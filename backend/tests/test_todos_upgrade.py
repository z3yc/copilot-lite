"""待办升级测试：分类 / 标签 / 全字段编辑 / AI 快速创建。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _get_categories(client, headers: dict) -> list[dict]:
    r = await client.get("/api/v1/todos/categories", headers=headers)
    assert r.status_code == 200
    return r.json()


@pytest.mark.asyncio
async def test_categories_defaults(authed_headers: dict) -> None:
    """新用户默认有 4 个分类。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cats = await _get_categories(client, authed_headers)
    assert len(cats) == 4
    names = {c["name"] for c in cats}
    assert names == {"工作", "生活", "学习", "其他"}


@pytest.mark.asyncio
async def test_todo_full_crud_with_category_tags(authed_headers: dict) -> None:
    """带分类和标签的完整增删改查。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cats = await _get_categories(client, authed_headers)
        work = next(c for c in cats if c["name"] == "工作")

        # 创建（含分类 + 标签）
        r = await client.post(
            "/api/v1/todos",
            json={
                "title": "写周报",
                "priority": 1,
                "category_id": work["id"],
                "tags": ["汇报", "重要"],
            },
            headers=authed_headers,
        )
        assert r.status_code == 200
        data = r.json()
        tid = data["id"]
        assert data["category_name"] == "工作"
        assert set(data["tags"]) == {"汇报", "重要"}

        # 分类过滤
        r = await client.get(f"/api/v1/todos?category_id={work['id']}", headers=authed_headers)
        assert any(x["id"] == tid for x in r.json())

        # 标签过滤
        r = await client.get("/api/v1/todos?tag=汇报", headers=authed_headers)
        assert any(x["id"] == tid for x in r.json())

        # 全字段编辑
        r = await client.patch(
            f"/api/v1/todos/{tid}",
            json={"title": "写月度周报", "priority": 2, "tags": ["汇报"]},
            headers=authed_headers,
        )
        assert r.json()["title"] == "写月度周报"
        assert r.json()["tags"] == ["汇报"]

        # 完成
        r = await client.patch(f"/api/v1/todos/{tid}", json={"status": "done"}, headers=authed_headers)
        assert r.json()["status"] == "done"

        # 删除
        r = await client.delete(f"/api/v1/todos/{tid}", headers=authed_headers)
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_ai_create_todo(monkeypatch, authed_headers: dict) -> None:
    """AI 快速创建：LLM 解析自然语言为结构化待办。"""
    import app.api.routes.todos as todos_module
    from app.core.llm import ChatResult

    class FakeAILLM:
        async def chat(self, messages, tools=None, temperature=0.7):
            return ChatResult(
                content='{"title": "买菜", "priority": 3, "due_date": "2026-08-26", "category": "生活", "tags": ["采购"]}'
            )

        async def close(self):
            pass

    monkeypatch.setattr(todos_module, "get_llm", lambda: FakeAILLM())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/todos/ai-create",
            json={"text": "明天下午3点买菜 生活 标签:采购"},
            headers=authed_headers,
        )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "买菜"
    assert data["category_name"] == "生活"
    assert data["due_date"] == "2026-08-26"
    assert data["tags"] == ["采购"]


@pytest.mark.asyncio
async def test_ai_create_fallback(monkeypatch, authed_headers: dict) -> None:
    """AI 解析失败时降级为整句标题。"""
    import app.api.routes.todos as todos_module
    from app.core.llm import ChatResult

    class BadAILLM:
        async def chat(self, messages, tools=None, temperature=0.7):
            return ChatResult(content="这不是JSON")

        async def close(self):
            pass

    monkeypatch.setattr(todos_module, "get_llm", lambda: BadAILLM())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/todos/ai-create", json={"text": "随便记一笔"}, headers=authed_headers
        )
    assert r.status_code == 200
    assert r.json()["title"] == "随便记一笔"


@pytest.mark.asyncio
async def test_ai_create_clamps_invalid_fields(monkeypatch, authed_headers: dict) -> None:
    """LLM 输出越界优先级/非法日期：夹取 1-5、日期置 None（不 500）。"""
    import app.api.routes.todos as todos_module
    from app.core.llm import ChatResult

    class WeirdAILLM:
        async def chat(self, messages, tools=None, temperature=0.7):
            return ChatResult(
                content='{"title": "怪数据", "priority": 99, "due_date": "明天下午"}'
            )

        async def close(self):
            pass

    monkeypatch.setattr(todos_module, "get_llm", lambda: WeirdAILLM())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/todos/ai-create", json={"text": "随便"}, headers=authed_headers
        )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "怪数据"
    assert data["priority"] == 5  # 99 → 夹取到 5
    assert data["due_date"] is None  # 非法日期 → None
