"""工具注册表与 Todo 工具的测试。"""

import pytest

from app.core.constants import DEFAULT_USER_ID
from app.tools import registry
from app.tools.base import ToolContext


def test_tools_registered() -> None:
    """核心工具均已注册。"""
    names = registry.names()
    assert "todo_create" in names
    assert "todo_list" in names
    assert "todo_complete" in names
    assert "todo_delete" in names


def test_schema_generation() -> None:
    """函数签名自动生成 JSON Schema：ctx 被排除，必填项正确。"""
    schema = registry.get("todo_create").to_openai_schema()
    params = schema["function"]["parameters"]
    assert "ctx" not in params["properties"]
    assert params["required"] == ["title"]
    assert params["properties"]["priority"]["default"] == 3


@pytest.mark.asyncio
async def test_todo_full_flow(db_session) -> None:
    """Todo 工具完整流程：创建 → 列表 → 完成 → 删除。"""
    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)

    # 创建
    created = await registry.execute(
        "todo_create", '{"title": "学习 FastAPI", "priority": 1}', ctx
    )
    assert '"status": "pending"' in created

    # 列表
    listed = await registry.execute("todo_list", "", ctx)
    assert "学习 FastAPI" in listed

    # 完成
    todo_id = created.split('"id": "')[1].split('"')[0]
    done = await registry.execute("todo_complete", f'{{"todo_id": "{todo_id}"}}', ctx)
    assert '"status": "done"' in done

    # 删除
    deleted = await registry.execute("todo_delete", f'{{"todo_id": "{todo_id}"}}', ctx)
    assert f'"deleted": "{todo_id}"' in deleted


@pytest.mark.asyncio
async def test_execute_unknown_tool(db_session) -> None:
    """未注册工具返回友好错误，不抛异常。"""
    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    result = await registry.execute("no_such_tool", "{}", ctx)
    assert "不存在" in result


@pytest.mark.asyncio
async def test_todo_create_with_category_tags(db_session) -> None:
    """todo_create 支持分类与标签。"""
    from app.models import Category

    cat = Category(user_id=DEFAULT_USER_ID, name="工作", color="#4f6ef7")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    result = await registry.execute(
        "todo_create",
        '{"title": "写报告", "category": "工作", "tags": ["汇报"]}',
        ctx,
    )
    assert '"title": "写报告"' in result
    assert '"tags": ["汇报"]' in result


@pytest.mark.asyncio
async def test_todo_update(db_session) -> None:
    """todo_update 修改任意字段。"""
    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    created = await registry.execute("todo_create", '{"title": "原标题"}', ctx)
    todo_id = created.split('"id": "')[1].split('"')[0]

    updated = await registry.execute(
        "todo_update",
        f'{{"todo_id": "{todo_id}", "title": "新标题", "priority": 1}}',
        ctx,
    )
    assert '"title": "新标题"' in updated
    assert '"priority": 1' in updated


@pytest.mark.asyncio
async def test_todo_list_by_category(db_session) -> None:
    """todo_list 支持分类过滤。"""
    from app.models import Category

    cat = Category(user_id=DEFAULT_USER_ID, name="学习", color="#f08c00")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    await registry.execute("todo_create", '{"title": "学Python", "category": "学习"}', ctx)
    await registry.execute("todo_create", '{"title": "买菜"}', ctx)

    listed = await registry.execute("todo_list", '{"category": "学习"}', ctx)
    assert "学Python" in listed
    assert "买菜" not in listed
