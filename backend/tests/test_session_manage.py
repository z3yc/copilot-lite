"""会话管理测试：重命名 / 搜索 / 导出 Markdown / 归属校验。"""

import uuid

from httpx import ASGITransport, AsyncClient

from app.main import app


async def _new_session(client: AsyncClient, headers: dict) -> str:
    resp = await client.post("/api/v1/sessions", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_rename_search_and_export(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid1 = await _new_session(client, authed_headers)
        sid2 = await _new_session(client, authed_headers)

        # 重命名
        resp = await client.patch(
            f"/api/v1/sessions/{sid1}",
            json={"title": "面试准备"},
            headers=authed_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == "面试准备"

        # 搜索：仅命中重命名后的会话
        resp = await client.get("/api/v1/sessions?q=面试", headers=authed_headers)
        ids = [s["id"] for s in resp.json()]
        assert sid1 in ids
        assert sid2 not in ids

        # 导出 Markdown
        resp = await client.get(
            f"/api/v1/sessions/{sid1}/export", headers=authed_headers
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.text.startswith("# 面试准备")


async def test_rename_other_users_session_returns_404(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = await _new_session(client, authed_headers)

        other = await client.post(
            "/api/v1/auth/register",
            json={"username": f"u{uuid.uuid4().hex[:8]}", "password": "secret123"},
        )
        other_headers = {"Authorization": f"Bearer {other.json()['token']}"}

        resp = await client.patch(
            f"/api/v1/sessions/{sid}",
            json={"title": "越权"},
            headers=other_headers,
        )
        assert resp.status_code == 404
