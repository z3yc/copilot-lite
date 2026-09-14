"""模型 Key 归属规则：普通用户一律自配；env Key 仅超级管理员可兜底。

设计：部署无需内置 Key；新注册账号（role=user）必须在前端「模型设置」配置
自己的 Key，禁止白嫖部署方 env Key。超级管理员（role=admin，如 seed 的 demo）
未自配时可用 env Key。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.routes.chat as chat_module
from app.core.config import settings
from app.core.db import async_session_factory
from app.core.llm import get_llm, set_llm_config
from app.core.llm_settings import apply_user_llm_config
from app.main import app
from app.models import User


async def _promote_admin(uid: str) -> None:
    """把已注册用户提升为超级管理员（模拟 seed 结果）。"""
    async with async_session_factory() as db:
        user = await db.get(User, uuid.UUID(uid))
        assert user is not None
        user.role = "admin"
        await db.commit()


async def _settings(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/settings/llm", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------- 普通用户（新增注册一律 role=user） ----------------


async def test_register_defaults_to_role_user(authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me", headers=authed_headers)
    assert resp.json()["data"]["role"] == "user"


async def test_normal_user_ignores_env_key(unconfigured_headers):
    """环境里有 Key 也不算新账号已配置：前端应弹引导。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        data = await _settings(client, unconfigured_headers)
    assert data["source"] == "none"
    assert data["api_key_set"] is False


async def test_normal_user_validate_raises_even_with_env(authed_headers, monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-env-should-be-ignored")
    set_llm_config(None)
    with pytest.raises(RuntimeError, match="模型设置"):
        chat_module._validate_llm_config()


async def test_normal_user_chat_without_key_returns_503(unconfigured_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat", json={"message": "你好"}, headers=unconfigured_headers
        )
    assert resp.status_code == 503
    assert "模型设置" in resp.json()["message"]


def test_get_llm_without_config_raises(monkeypatch):
    """无上下文配置时 get_llm 必须报错（不得偷偷用 env Key）。"""
    from app.core import llm as llm_module

    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-env-should-be-ignored")
    set_llm_config(None)
    with pytest.raises(RuntimeError, match="未配置模型"):
        llm_module.get_llm()


# ---------------- 超级管理员（唯一可用 env 兜底） ----------------


async def test_admin_uses_env_key(unconfigured_headers):
    uid = unconfigured_headers["uid"]
    await _promote_admin(uid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        data = await _settings(client, unconfigured_headers)
    assert data["source"] == "env"
    assert data["api_key_set"] is True

    async with async_session_factory() as db:
        await apply_user_llm_config(db, uuid.UUID(uid))
    chat_module._validate_llm_config()  # 不抛
    assert get_llm().model == settings.DEEPSEEK_MODEL


async def test_admin_personal_key_wins(authed_headers):
    """管理员自配 Key 时优先用自己的，而非 env。"""
    uid = authed_headers["uid"]
    await _promote_admin(uid)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        put = await client.put(
            "/api/v1/settings/llm",
            json={
                "base_url": "https://api.example.com",
                "model": "admin-own-model",
                "api_key": "sk-admin-own-key",
            },
            headers=authed_headers,
        )
        assert put.json()["data"]["source"] == "user"
        data = await _settings(client, authed_headers)
    assert data["source"] == "user"
    assert data["model"] == "admin-own-model"


# ---------------- 超级管理员种子 ----------------


async def test_seed_super_admin_creates_admin(db_session, monkeypatch):
    monkeypatch.setattr(settings, "SUPER_ADMIN_USERNAME", "demo")
    monkeypatch.setattr(settings, "SUPER_ADMIN_PASSWORD", "demo-pass-123")
    from app.main import _seed_super_admin

    await _seed_super_admin()

    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.username == "demo"))
    assert user is not None and user.role == "admin"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "demo", "password": "demo-pass-123"},
        )
    assert login.status_code == 200, login.text


async def test_seed_super_admin_skipped_without_password(db_session, monkeypatch):
    monkeypatch.setattr(settings, "SUPER_ADMIN_USERNAME", "demo-nopass")
    monkeypatch.setattr(settings, "SUPER_ADMIN_PASSWORD", "")
    from app.main import _seed_super_admin

    await _seed_super_admin()

    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.username == "demo-nopass"))
    assert user is None
