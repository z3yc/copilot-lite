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
    data = r.json()["data"]
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


@pytest.mark.asyncio
async def test_login_rate_limit(authed_headers: dict, monkeypatch) -> None:
    """登录限流：同一用户名连续失败 5 次后，第 6 次即使密码正确也返回 429。"""
    import app.api.routes.auth as auth_module

    monkeypatch.setattr(auth_module, "_login_attempts", {})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(auth_module._LOGIN_MAX_ATTEMPTS):
            r = await client.post(
                "/api/v1/auth/login",
                json={"username": "ratelimituser", "password": "wrongpass"},
            )
            assert r.status_code == 401

        # 窗口已满：即使密码正确也拒绝（防爆破）
        r = await client.post(
            "/api/v1/auth/login",
            json={"username": "ratelimituser", "password": "wrongpass"},
        )
        assert r.status_code == 429


@pytest.mark.asyncio
async def test_change_password_invalidates_old_token(authed_headers: dict) -> None:
    """改密后旧 token 立即失效（token_version 校验），新密码可登录。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 改密前旧 token 可用
        r = await client.get("/api/v1/auth/me", headers=authed_headers)
        assert r.status_code == 200
        username = r.json()["data"]["username"]

        # 改密
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "secret123", "new_password": "newpass123"},
            headers=authed_headers,
        )
        assert r.status_code == 200

        # 旧 token 立即 401
        r = await client.get("/api/v1/auth/me", headers=authed_headers)
        assert r.status_code == 401

        # 新密码登录后新 token 可用
        r = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "newpass123"},
        )
        assert r.status_code == 200
        new_token = r.json()["data"]["token"]
        r = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"}
        )
        assert r.status_code == 200
