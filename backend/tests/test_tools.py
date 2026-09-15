"""工具注册表与 Todo 工具的测试。"""

import uuid

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


def test_schema_optional_types_mapped() -> None:
    """Optional/int|None 注解应剥壳映射为正确 JSON 类型（回归：曾误判为 string）。"""
    schema = registry.get("todo_update").to_openai_schema()
    props = schema["function"]["parameters"]["properties"]
    assert props["priority"]["type"] == "integer"
    assert props["status"]["type"] == "string"
    assert props["tags"]["type"] == "array"


def test_schema_priority_semantics_in_description() -> None:
    """工具描述必须写清优先级语义（1 最高、5 最低），避免 LLM 认知颠倒。"""
    for name in ("todo_create", "todo_update"):
        desc = registry.get(name).to_openai_schema()["function"]["description"]
        assert "1 最高" in desc and "5 最低" in desc


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
async def test_todo_update_priority_string_coerced(db_session) -> None:
    """LLM 把优先级传成字符串 "5" 时也能正确更新（类型容错，回归 #21）。"""
    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    created = await registry.execute("todo_create", '{"title": "炒股", "priority": 3}', ctx)
    todo_id = created.split('"id": "')[1].split('"')[0]

    # 模拟 LLM 工具调用：priority 是字符串
    updated = await registry.execute(
        "todo_update",
        f'{{"todo_id": "{todo_id}", "priority": "5"}}',
        ctx,
    )
    assert '"priority": 5' in updated

    # 数据库确认真实落库（此前 TypeError 在 commit 前抛出导致"看似未更新"）
    from sqlalchemy import select

    from app.models import Todo

    todo = (await db_session.scalars(select(Todo).where(Todo.id == uuid.UUID(todo_id)))).one()
    assert todo.priority == 5


@pytest.mark.asyncio
async def test_todo_create_priority_and_tags_string_coerced(db_session) -> None:
    """todo_create 字符串整数/字符串数组参数均被转换为正确类型。"""
    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    result = await registry.execute(
        "todo_create",
        '{"title": "类型容错", "priority": "2", "tags": "[\\"a\\", \\"b\\"]"}',
        ctx,
    )
    assert '"priority": 2' in result
    assert '"tags": ["a", "b"]' in result


@pytest.mark.asyncio
async def test_todo_update_priority_invalid_string(db_session) -> None:
    """无法转换的参数返回友好错误，不抛异常、不改数据。"""
    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    created = await registry.execute("todo_create", '{"title": "保持3", "priority": 3}', ctx)
    todo_id = created.split('"id": "')[1].split('"')[0]

    result = await registry.execute(
        "todo_update",
        f'{{"todo_id": "{todo_id}", "priority": "abc"}}',
        ctx,
    )
    assert "参数不合法" in result
    assert "错误" in result

    from sqlalchemy import select

    from app.models import Todo

    todo = (await db_session.scalars(select(Todo).where(Todo.id == uuid.UUID(todo_id)))).one()
    assert todo.priority == 3  # 未受影响


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


@pytest.mark.asyncio
async def test_todo_tools_reject_foreign_user(db_session, make_user) -> None:
    """工具层归属校验：用户 B 不能改/完成/删除用户 A 的待办（回归：授权不对称）。"""
    from sqlalchemy import select

    from app.models import Todo

    user_a, user_b = await make_user(), await make_user()
    ctx_a = ToolContext(session=db_session, user_id=user_a)
    created = await registry.execute("todo_create", '{"title": "A的私密待办"}', ctx_a)
    todo_id = created.split('"id": "')[1].split('"')[0]

    ctx_b = ToolContext(session=db_session, user_id=user_b)
    for name, args in [
        ("todo_update", f'{{"todo_id": "{todo_id}", "title": "被篡改"}}'),
        ("todo_complete", f'{{"todo_id": "{todo_id}"}}'),
        ("todo_delete", f'{{"todo_id": "{todo_id}"}}'),
    ]:
        result = await registry.execute(name, args, ctx_b)
        assert "无权限" in result, f"{name} 应拒绝跨用户操作"

    todo = (await db_session.scalars(select(Todo).where(Todo.id == uuid.UUID(todo_id)))).one()
    assert todo.title == "A的私密待办"  # 未被篡改
    assert todo.status == "pending"  # 未被完成/删除
