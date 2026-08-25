"""聊天 API 集成测试：FakeLLM 替换真实模型。"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.routes.chat as chat_module
from app.core.db import Base, async_session_factory, engine
from app.core.llm import ChatResult
from app.main import app


class FakeLLM:
    """按预设顺序返回响应的假模型。"""

    def __init__(self, replies: list[ChatResult]) -> None:
        self.replies = list(replies)

    async def chat(self, messages, tools=None, temperature=0.7) -> ChatResult:
        return self.replies.pop(0)

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_chat_creates_session_and_persists(monkeypatch) -> None:
    """POST /chat：新会话创建、消息持久化、返回回复。"""
    # 准备测试库表结构（lifespan 不会在测试中触发）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    fake = FakeLLM([ChatResult(content="你好！我是你的 AI 助理")])
    monkeypatch.setattr(chat_module, "get_llm", lambda: fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"message": "你好"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == "你好！我是你的 AI 助理"
    assert data["session_id"]

    # 验证消息已持久化
    async with async_session_factory() as session:
        from app.models import Message

        rows = (await session.scalars(select(Message))).all()
        roles = [m.role for m in rows]
        assert roles == ["user", "assistant"]


@pytest.mark.asyncio
async def test_chat_continues_session(monkeypatch) -> None:
    """携带 session_id 时续接同一会话。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    fake = FakeLLM([ChatResult(content="第一轮"), ChatResult(content="第二轮")])
    monkeypatch.setattr(chat_module, "get_llm", lambda: fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/api/v1/chat", json={"message": "第一条"})
        sid = r1.json()["session_id"]
        r2 = await client.post("/api/v1/chat", json={"message": "第二条", "session_id": sid})

    assert r2.status_code == 200
    assert r2.json()["session_id"] == sid
    assert r2.json()["reply"] == "第二轮"


@pytest.mark.asyncio
async def test_chat_requires_key(monkeypatch) -> None:
    """未配置 API Key 时返回 503 与清晰提示。"""
    # 路由会先创建会话再检查 Key，因此需要表结构
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    def _no_key():
        raise RuntimeError("未配置 DEEPSEEK_API_KEY：请在 backend/.env 中设置")

    monkeypatch.setattr(chat_module, "get_llm", _no_key)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"message": "你好"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_chat_stream_sse(monkeypatch) -> None:
    """SSE 流式：session → chunk... → done 事件序列。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    fake = FakeLLM([ChatResult(content="你好，这是流式回复的测试内容。" * 3)])
    monkeypatch.setattr(chat_module, "get_llm", lambda: fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST", "/api/v1/chat/stream", json={"message": "你好"}
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            events: list[str] = []
            session_id: str | None = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line[7:])
                elif line.startswith("data: ") and "session_id" in line:
                    import json as _json

                    session_id = _json.loads(line[6:])["session_id"]

    # 事件序列校验
    assert events[0] == "session"
    assert events[-1] == "done"
    assert "chunk" in events
    assert session_id
