"""API 限流测试：chat / ai-create 按用户维度滑动窗口，超频 429。"""

import time

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes.chat as chat_module
import app.api.routes.todos as todos_module
import app.core.rate_limit as rl
from app.core.llm import ChatResult
from app.main import app


class _FakeLLM:
    def __init__(self, content: str = "好的") -> None:
        self.content = content

    async def chat(self, messages, tools=None, temperature=0.7):
        return ChatResult(content=self.content)

    async def close(self) -> None:
        pass


def test_limiter_window_slides() -> None:
    """限流器单元：窗口内超限拒绝，窗口滑过后恢复放行。"""
    limiter = rl.SlidingWindowLimiter(2, 0.05)
    assert limiter.allow("k")
    assert limiter.allow("k")
    assert not limiter.allow("k")
    # 睡眠余量放大到窗口的 4 倍（0.2s vs 0.05s）：CI 全量负载下 0.06s 曾偶发不足
    time.sleep(0.2)
    assert limiter.allow("k")


@pytest.mark.asyncio
async def test_chat_rate_limited(monkeypatch, authed_headers: dict) -> None:
    """对话接口：窗口内前 2 次正常，第 3 次 429。"""
    monkeypatch.setattr(chat_module, "chat_limiter", rl.SlidingWindowLimiter(2, 60))
    monkeypatch.setattr(chat_module, "get_llm", lambda: _FakeLLM())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            r = await client.post(
                "/api/v1/chat", json={"message": "你好"}, headers=authed_headers
            )
            assert r.status_code == 200
        r = await client.post(
            "/api/v1/chat", json={"message": "你好"}, headers=authed_headers
        )
        assert r.status_code == 429


@pytest.mark.asyncio
async def test_ai_create_rate_limited(monkeypatch, authed_headers: dict) -> None:
    """AI 解析待办接口：窗口内第 2 次 429。"""
    monkeypatch.setattr(todos_module, "ai_create_limiter", rl.SlidingWindowLimiter(1, 60))
    monkeypatch.setattr(todos_module, "get_llm", lambda: _FakeLLM(content='{"title": "买菜"}'))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/todos/ai-create", json={"text": "买菜"}, headers=authed_headers
        )
        assert r.status_code == 200
        r = await client.post(
            "/api/v1/todos/ai-create", json={"text": "买菜"}, headers=authed_headers
        )
        assert r.status_code == 429
