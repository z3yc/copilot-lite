"""模型配置页面化测试：加密、掩码、按用户生效、环境回退、连通性测试、隔离。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.db import async_session_factory
from app.core.llm import LLMConfig, build_llm, env_llm_config
from app.core.llm_settings import resolve_user_llm_config
from app.main import app
from app.models import LLMSetting

# ---------------- 加密/掩码 ----------------


def test_encrypt_decrypt_roundtrip():
    token = encrypt_secret("sk-secret-abcdefgh")
    assert token != "sk-secret-abcdefgh"
    assert decrypt_secret(token) == "sk-secret-abcdefgh"


def test_decrypt_invalid_returns_empty():
    assert decrypt_secret("not-a-token") == ""


def test_mask_secret():
    assert mask_secret("sk-secret-abcdefgh") == "sk-****efgh"
    assert mask_secret("short") == "*****"
    assert mask_secret("") == ""


def test_build_llm_applies_config():
    config = LLMConfig(
        api_key="k", base_url="http://x", model="m", temperature=0.3, max_tokens=99
    )
    client = build_llm(config)
    assert client.model == "m"
    assert client._max_tokens() == 99
    assert client._temperature(None) == 0.3


def test_env_llm_config_present_in_tests():
    # 测试环境设置了假 DEEPSEEK_API_KEY
    env = env_llm_config()
    assert env is not None and env.api_key


# ---------------- 接口 ----------------


async def test_get_returns_env_by_default(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/settings/llm", headers=authed_headers)
    body = resp.json()["data"]
    assert resp.status_code == 200
    assert body["source"] == "env"
    assert body["api_key_set"] is True


async def test_save_get_delete_and_encrypted_at_rest(authed_headers: dict) -> None:
    uid = uuid.UUID(authed_headers["uid"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        put = await client.put(
            "/api/v1/settings/llm",
            json={
                "base_url": "https://api.example.com",
                "model": "my-model",
                "api_key": "sk-secret-12345678",
                "temperature": 0.5,
                "max_tokens": 1024,
            },
            headers=authed_headers,
        )
        assert put.status_code == 200, put.text
        assert "sk-secret-12345678" not in put.text  # 永不回传明文
        body = put.json()["data"]
        assert body["source"] == "user"
        assert body["api_key_preview"] == "sk-****5678"

        got = await client.get("/api/v1/settings/llm", headers=authed_headers)
        assert got.json()["data"]["model"] == "my-model"

        # 删除 → 回退环境
        await client.delete("/api/v1/settings/llm", headers=authed_headers)
        after = await client.get("/api/v1/settings/llm", headers=authed_headers)
        assert after.json()["data"]["source"] == "env"

    # 入库为密文（用保存前的状态另存一次校验）
    async with async_session_factory() as db:
        row = await db.scalar(select(LLMSetting).where(LLMSetting.user_id == uid))
        assert row is None  # 已删除


async def test_stored_key_is_encrypted(authed_headers: dict) -> None:
    uid = uuid.UUID(authed_headers["uid"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.put(
            "/api/v1/settings/llm",
            json={
                "base_url": "https://api.example.com",
                "model": "my-model",
                "api_key": "sk-plaintext-9999",
            },
            headers=authed_headers,
        )
    async with async_session_factory() as db:
        row = await db.scalar(select(LLMSetting).where(LLMSetting.user_id == uid))
        assert row is not None
        assert row.api_key_encrypted is not None
        assert "sk-plaintext-9999" not in row.api_key_encrypted
        assert decrypt_secret(row.api_key_encrypted) == "sk-plaintext-9999"


async def test_cross_user_isolation(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.put(
            "/api/v1/settings/llm",
            json={
                "base_url": "https://api.example.com",
                "model": "user1-model",
                "api_key": "sk-user1-key-xxxx",
            },
            headers=authed_headers,
        )
        other = await client.post(
            "/api/v1/auth/register",
            json={"username": f"u{uuid.uuid4().hex[:8]}", "password": "secret123"},
        )
        other_headers = {"Authorization": f"Bearer {other.json()['data']['token']}"}
        got = await client.get("/api/v1/settings/llm", headers=other_headers)
    assert got.json()["data"]["source"] == "env"  # 看不到用户1的配置
    assert got.json()["data"]["model"] != "user1-model"


async def test_invalid_base_url_rejected(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            "/api/v1/settings/llm",
            json={"base_url": "ftp://bad", "model": "m", "api_key": "k"},
            headers=authed_headers,
        )
    assert resp.status_code == 422


async def test_resolve_user_config(authed_headers: dict) -> None:
    uid = uuid.UUID(authed_headers["uid"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.put(
            "/api/v1/settings/llm",
            json={
                "base_url": "https://api.example.com",
                "model": "resolve-model",
                "api_key": "sk-resolve-key",
            },
            headers=authed_headers,
        )
    async with async_session_factory() as db:
        config = await resolve_user_llm_config(db, uid)
    assert config is not None
    assert config.model == "resolve-model"
    assert config.api_key == "sk-resolve-key"


async def test_connection_test_ok_and_fail(monkeypatch, authed_headers: dict) -> None:
    from app.api.routes import settings as settings_module

    class FakeLLM:
        async def chat(self, messages, tools=None, temperature=None, response_format=None):
            from app.core.llm import ChatResult

            return ChatResult(content="pong")

    class BadLLM:
        async def chat(self, messages, tools=None, temperature=None, response_format=None):
            raise RuntimeError("invalid api key")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        monkeypatch.setattr(settings_module, "build_llm", lambda cfg: FakeLLM())
        ok = await client.post(
            "/api/v1/settings/llm/test",
            json={"base_url": "https://api.example.com", "model": "m", "api_key": "sk-x"},
            headers=authed_headers,
        )
        assert ok.json()["data"]["ok"] is True

        monkeypatch.setattr(settings_module, "build_llm", lambda cfg: BadLLM())
        bad = await client.post(
            "/api/v1/settings/llm/test",
            json={"base_url": "https://api.example.com", "model": "m", "api_key": "sk-x"},
            headers=authed_headers,
        )
        assert bad.json()["data"]["ok"] is False
        assert "连接失败" in bad.json()["data"]["message"]
