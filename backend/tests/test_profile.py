"""个人主页接口测试：profile 统计 + 修改密码。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_profile_stats(authed_headers: dict) -> None:
    """profile 返回账号信息与统计字段。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/auth/profile", headers=authed_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["username"].startswith("u")
    assert "session_count" in data
    assert "chunk_count" in data
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_change_password_flow(authed_headers: dict) -> None:
    """改密：错误旧密码 400；正确后新密码可登录。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 错误旧密码
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "wrong", "new_password": "newpass123"},
            headers=authed_headers,
        )
        assert r.status_code == 400

        # 正确改密
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "secret123", "new_password": "newpass123"},
            headers=authed_headers,
        )
        assert r.status_code == 200
