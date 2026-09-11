"""列表分页测试：参数夹取 + 待办分页行为。"""

import uuid

from httpx import ASGITransport, AsyncClient

from app.core.db import async_session_factory
from app.core.pagination import MAX_PAGE_SIZE, normalize_page, page_offset
from app.main import app
from app.models import Todo


def test_normalize_page_clamps():
    assert normalize_page(1, 20) == (1, 20)
    assert normalize_page(0, 20) == (1, 20)
    assert normalize_page(2, 1000) == (2, MAX_PAGE_SIZE)
    assert normalize_page(2, 0) == (2, 1)


def test_page_offset():
    assert page_offset(1, 10) == (0, 10)
    assert page_offset(2, 10) == (10, 10)
    assert page_offset(0, 0) == (0, 1)


async def test_todos_pagination(authed_headers: dict) -> None:
    uid = uuid.UUID(authed_headers["uid"])
    async with async_session_factory() as db:
        for i in range(25):
            db.add(Todo(user_id=uid, title=f"任务{i}", priority=3))
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 第 2 页，每页 10 条
        resp = await client.get(
            "/api/v1/todos?page=2&page_size=10", headers=authed_headers
        )
        body = resp.json()["data"]
        assert body["total"] == 25
        assert body["page"] == 2
        assert body["page_size"] == 10
        assert len(body["items"]) == 10

        # page_size 超上限被夹取到 100
        resp = await client.get(
            "/api/v1/todos?page=1&page_size=1000", headers=authed_headers
        )
        body = resp.json()["data"]
        assert body["page_size"] == MAX_PAGE_SIZE
        assert len(body["items"]) == 25


async def test_sessions_pagination(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            await client.post("/api/v1/sessions", json={}, headers=authed_headers)
        resp = await client.get(
            "/api/v1/sessions?page=1&page_size=2", headers=authed_headers
        )
    body = resp.json()["data"]
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page_size"] == 2
