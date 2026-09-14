"""管理后台鉴权测试：未认证 401 / 普通用户 403 / 管理员放行。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _get(path: str, headers: dict | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers or {})


@pytest.mark.asyncio
async def test_admin_requires_auth() -> None:
    """未携带 token 访问 /admin 返回 401。"""
    r = await _get("/api/v1/admin/ping")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_forbids_normal_user(authed_headers: dict) -> None:
    """普通用户访问 /admin 返回 403（非管理员一律拒绝）。"""
    r = await _get("/api/v1/admin/ping", authed_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_allows_admin(admin_headers: dict) -> None:
    """管理员访问 /admin 放行，返回骨架探针。"""
    r = await _get("/api/v1/admin/ping", admin_headers)
    assert r.status_code == 200
    assert r.json()["data"]["ok"] is True


@pytest.mark.asyncio
async def test_admin_disabled_returns_404(admin_headers: dict, monkeypatch) -> None:
    """ADMIN_ENABLED=false 时，/admin 对管理员也返回 404（功能整体关闭）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_ENABLED", False)
    r = await _get("/api/v1/admin/ping", admin_headers)
    assert r.status_code == 404
