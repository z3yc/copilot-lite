"""流式心跳：长静默期不得截断回答，也不得把截断当成 done。

回归对象：`asyncio.wait_for(anext(gen), ...)` 超时会取消生成器，导致
「静默 > 心跳间隔」的轮次被静默截断、且仍发 done。
"""

import asyncio
import json
import uuid
from typing import ClassVar

from httpx import ASGITransport, AsyncClient

from app.main import app


class _SlowStreamAgent:
    """模拟长静默期的流式产出：分片之间 sleep 超过心跳间隔。"""

    last_tool_calls: ClassVar[list] = []
    pending_confirmation: ClassVar[list] = []
    last_citations: ClassVar[list] = [
        {"index": 1, "chunk_id": "c1", "source": "文档X", "snippet": "s"}
    ]
    last_trajectory: ClassVar[dict] = {
        "engine": "langgraph",
        "total_ms": 1,
        "truncated": False,
        "steps": [{"type": "answer", "chars": 4}],
    }

    def __init__(self, parts: list[str], gap: float) -> None:
        self._parts = parts
        self._gap = gap

    async def run_stream(self, **kwargs):
        for p in self._parts:
            await asyncio.sleep(self._gap)
            yield p

    async def close(self) -> None:
        pass


async def _drain(client, headers) -> tuple[list[str], dict, list[str], list[str]]:
    events: list[str] = []
    texts: list[str] = []
    done: dict = {}
    errors: list[str] = []
    async with client.stream(
        "POST", "/api/v1/chat/stream", json={"message": "长静默测试"}, headers=headers
    ) as resp:
        event = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event = line[7:]
                events.append(event)
            elif line.startswith("data: "):
                payload = json.loads(line[6:])
                if event == "chunk" and "text" in payload:
                    texts.append(payload["text"])
                elif event == "done":
                    done = payload
                elif event == "error":
                    errors.append(payload.get("detail", ""))
    return events, done, texts, errors


async def test_slow_round_is_not_truncated(monkeypatch, authed_headers):
    """分片间隔 > 心跳间隔时，全部分片都要到达，且要发 done。"""
    from app.api.routes import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_HEARTBEAT_SECONDS", 0.05)
    agent = _SlowStreamAgent(["第一段", "第二段", "第三段"], gap=0.15)
    monkeypatch.setattr(chat_mod, "_build_agent", lambda: agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        events, _done, texts, errors = await _drain(client, authed_headers)

    assert "".join(texts) == "第一段第二段第三段", f"回答被截断：{texts!r}"
    assert "done" in events and not errors


async def test_slow_round_keeps_trajectory_and_citations(monkeypatch, authed_headers):
    """收尾代码必须跑到：citations 与 trajectory 都要落库（截断时两者会一起丢）。"""
    from app.api.routes import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_HEARTBEAT_SECONDS", 0.05)
    agent = _SlowStreamAgent(["完整回答"], gap=0.15)
    monkeypatch.setattr(chat_mod, "_build_agent", lambda: agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, _, _, _ = await _drain(client, authed_headers)
        page = (await client.get("/api/v1/sessions", headers=authed_headers)).json()["data"]
        sid = page["items"][0]["id"]
        msgs = (
            await client.get(f"/api/v1/sessions/{sid}/messages", headers=authed_headers)
        ).json()["data"]

    extra = msgs[-1].get("extra") or {}
    assert "citations" in extra, "收尾未执行：citations 丢失"
    assert "trajectory" in extra, "收尾未执行：trajectory 丢失"
    assert msgs[-1]["content"] == "完整回答"


async def test_stream_cap_emits_error_not_done(monkeypatch, authed_headers):
    """真正挂死的生成器由总时长上限兜底：发 error，绝不发 done。"""
    from app.api.routes import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_HEARTBEAT_SECONDS", 0.02)
    monkeypatch.setattr(chat_mod, "_STREAM_MAX_SECONDS", 0.05)
    agent = _SlowStreamAgent(["永不产出"], gap=5.0)
    monkeypatch.setattr(chat_mod, "_build_agent", lambda: agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        events, _, texts, errors = await _drain(client, authed_headers)

    assert "error" in events and "done" not in events
    assert texts == []
    assert errors


async def test_disconnect_closes_engine_generator(monkeypatch, authed_headers, db_session):
    """客户端断开后必须关掉引擎生成器（否则悬挂任务持有引擎）。"""
    from app.api.routes import chat as chat_mod
    from app.api.routes.chat import ChatRequest
    from app.models import User

    closed = asyncio.Event()

    class _StuckAgent:
        last_tool_calls: ClassVar[list] = []
        pending_confirmation: ClassVar[list] = []
        last_citations: ClassVar[list] = []
        last_trajectory: ClassVar[dict] = {}

        async def run_stream(self, **kwargs):
            try:
                yield "第一段"
                await asyncio.sleep(30)  # 长静默：等客户端断开
                yield "第二段"
            finally:
                closed.set()  # 生成器被关闭时才置位

        async def close(self) -> None:
            pass

    monkeypatch.setattr(chat_mod, "_build_agent", lambda: _StuckAgent())

    # 直接驱动事件生成器，绕开 ASGI 传输对断开语义的依赖
    user = await db_session.get(User, uuid.UUID(authed_headers["uid"]))
    response = await chat_mod.chat_stream(
        ChatRequest(message="断开测试"), db=db_session, user=user, _quota=None
    )
    gen = response.body_iterator
    while True:  # 消费到首个 chunk，确保引擎的 anext 已在飞（挂在 sleep 上）
        event = await anext(gen)
        if "event: chunk" in event:
            break
    await gen.aclose()  # 客户端断开

    await asyncio.wait_for(closed.wait(), timeout=5)
    assert closed.is_set(), "断开后引擎生成器未被关闭（悬挂任务）"


async def test_cap_path_closes_producer_before_persist(monkeypatch, authed_headers):
    """静默上限路径：必须先取消并等待生产者，再落库部分回复。

    生产者可能仍挂在 registry.execute（持有同一个 AsyncSession）上；若不等它真正结束
    就落库，两者会并发使用同一 session（SQLAlchemy 异步 session 禁止并发使用，
    失败还会被兜底 except 吞掉）。
    观测点：生产者 finally 是否先置位，再调用 _persist_partial（顺序敏感）。
    """
    from app.api.routes import chat as chat_mod

    closed = asyncio.Event()
    captured: list[bool] = []

    class _StuckAfterFirstAgent:
        last_tool_calls: ClassVar[list] = []
        pending_confirmation: ClassVar[list] = []
        last_citations: ClassVar[list] = []
        last_trajectory: ClassVar[dict] = {}

        async def run_stream(self, **kwargs):
            try:
                yield "部分"
                await asyncio.sleep(30)  # 卡在 await（模拟 registry.execute 持 session）
                yield "永不产出"
            finally:
                closed.set()  # 生产者真正结束才置位

        async def close(self) -> None:
            pass

    async def _capture_persist(db, session_id, reply_parts):
        # 同步捕获（函数体首个 await 之前），记录落库时刻生产者是否已关闭
        captured.append(closed.is_set())

    monkeypatch.setattr(chat_mod, "_build_agent", lambda: _StuckAfterFirstAgent())
    monkeypatch.setattr(chat_mod, "_persist_partial", _capture_persist)
    monkeypatch.setattr(chat_mod, "_HEARTBEAT_SECONDS", 0.02)
    monkeypatch.setattr(chat_mod, "_STREAM_MAX_SECONDS", 0.05)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        events, _, texts, _errors = await _drain(client, authed_headers)

    assert "error" in events and "done" not in events
    assert texts == ["部分"], f"部分回复应已在落库前产出：{texts!r}"
    assert captured == [True], (
        f"落库时生产者尚未真正结束：captured={captured}，closed={closed.is_set()}"
    )
