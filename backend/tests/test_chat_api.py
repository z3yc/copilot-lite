"""聊天 API 集成测试（需认证）：FakeLLM 替换真实模型。"""

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from sqlalchemy import select

import app.api.routes.chat as chat_module
from app.core.db import async_session_factory
from app.core.llm import ChatResult
from app.main import app
from app.tools import registry


class _FakeDelta:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls = None


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.delta = _FakeDelta(content)


class _FakeChunk:
    """模拟 openai 流式 chunk。"""

    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeStream:
    """可 await 返回的异步迭代器（模拟 openai 流式对象）。"""

    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeLLM:
    """按预设顺序返回响应的假模型。"""

    def __init__(self, replies: list[ChatResult]) -> None:
        self.replies = list(replies)

    async def chat(self, messages, tools=None, temperature=0.7) -> ChatResult:
        return self.replies.pop(0)

    async def stream_raw(self, messages, tools=None, temperature=0.7):
        """流式模拟：把回复内容按 3 字符切成 chunk。"""
        text = self.replies.pop(0).content or ""
        chunks = [_FakeChunk(text[i : i + 3]) for i in range(0, len(text), 3)]
        return _FakeStream(chunks)

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_chat_creates_session_and_persists(monkeypatch, authed_headers: dict) -> None:
    """POST /chat：新会话创建、消息持久化、返回回复。"""
    fake = FakeLLM([ChatResult(content="你好！我是你的 AI 助理")])
    monkeypatch.setattr(chat_module, "get_llm", lambda: fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"message": "你好"}, headers=authed_headers)
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
async def test_chat_continues_session(monkeypatch, authed_headers: dict) -> None:
    """携带 session_id 时续接同一会话。"""
    fake = FakeLLM([ChatResult(content="第一轮"), ChatResult(content="第二轮")])
    monkeypatch.setattr(chat_module, "get_llm", lambda: fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/api/v1/chat", json={"message": "第一条"}, headers=authed_headers)
        sid = r1.json()["session_id"]
        r2 = await client.post(
            "/api/v1/chat",
            json={"message": "第二条", "session_id": sid},
            headers=authed_headers,
        )

    assert r2.status_code == 200
    assert r2.json()["session_id"] == sid
    assert r2.json()["reply"] == "第二轮"


@pytest.mark.asyncio
async def test_chat_requires_key(monkeypatch, authed_headers: dict) -> None:
    """未配置 API Key 时返回 503 与清晰提示。"""

    def _no_key():
        raise RuntimeError("未配置 DEEPSEEK_API_KEY：请在 backend/.env 中设置")

    monkeypatch.setattr(chat_module, "get_llm", _no_key)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"message": "你好"}, headers=authed_headers)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_chat_stream_sse(monkeypatch, authed_headers: dict) -> None:
    """SSE 流式：session → chunk... → done 事件序列。"""
    fake = FakeLLM([ChatResult(content="你好，这是流式回复的测试内容。" * 3)])
    monkeypatch.setattr(chat_module, "get_llm", lambda: fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST", "/api/v1/chat/stream", json={"message": "你好"}, headers=authed_headers
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


@pytest.mark.asyncio
async def test_chat_stream_error_event_and_user_persisted(monkeypatch, authed_headers: dict) -> None:
    """流式生成中途异常：发 error 事件（不裸断），且用户消息已先落库。"""

    class BoomLLM:
        async def chat(self, messages, tools=None, temperature=0.7):
            raise RuntimeError("模型挂了")

        async def stream_raw(self, messages, tools=None, temperature=0.7):
            raise RuntimeError("模型挂了")

        async def close(self) -> None:
            pass

    monkeypatch.setattr(chat_module, "get_llm", lambda: BoomLLM())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST", "/api/v1/chat/stream", json={"message": "你好"}, headers=authed_headers
        ) as resp:
            assert resp.status_code == 200
            events: list[str] = []
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line[7:])

    # 通用异常也必须有显式 error 终态
    assert events[0] == "session"
    assert events[-1] == "error"

    # 用户消息先落库：流中断不丢用户输入
    async with async_session_factory() as session:
        from app.models import Message

        rows = (await session.scalars(select(Message))).all()
        assert [m.role for m in rows] == ["user"]


# ---------------- LangGraph 引擎（经 API 全链路） ----------------


class _FakeLangChainLLM(GenericFakeChatModel):
    """支持 bind_tools 的假模型（不触网）。"""

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.mark.asyncio
async def test_chat_uses_langgraph_engine(monkeypatch, authed_headers: dict) -> None:
    """默认引擎 LangGraph：POST /chat 走 Supervisor 路由 + 子 Agent 回复。"""
    from app.agent.langgraph_engine import LangGraphEngine

    fake = _FakeLangChainLLM(
        messages=iter(
            [
                AIMessage(content='{"route": "chat", "reason": "测试"}'),
                AIMessage(content="LangGraph 引擎回复"),
            ]
        )
    )
    monkeypatch.setattr(
        chat_module, "_build_agent", lambda: LangGraphEngine(llm=fake, registry=registry)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"message": "你好"}, headers=authed_headers)
    assert resp.status_code == 200
    assert resp.json()["reply"] == "LangGraph 引擎回复"


@pytest.mark.asyncio
async def test_chat_stream_langgraph_engine(monkeypatch, authed_headers: dict) -> None:
    """LangGraph 引擎经 SSE 流式输出（session → chunk → done，接口不变）。"""
    from app.agent.langgraph_engine import LangGraphEngine

    fake = _FakeLangChainLLM(
        messages=iter(
            [
                AIMessage(content='{"route": "chat", "reason": "测试"}'),
                AIMessage(content="流式回复"),
            ]
        )
    )
    monkeypatch.setattr(
        chat_module, "_build_agent", lambda: LangGraphEngine(llm=fake, registry=registry)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST", "/api/v1/chat/stream", json={"message": "你好"}, headers=authed_headers
        ) as resp:
            assert resp.status_code == 200
            events: list[str] = []
            text_parts: list[str] = []
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line[7:])
                elif line.startswith("data: ") and '"text"' in line:
                    import json as _json

                    text_parts.append(_json.loads(line[6:])["text"])

    assert events[0] == "session" and events[-1] == "done"
    assert "".join(text_parts) == "流式回复"
