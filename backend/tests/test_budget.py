"""LLM 成本预算与 token 计量测试。"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes.chat as chat_module
import app.core.budget as budget_module
import app.core.llm as llm_module
from app.core.budget import add_token_usage, check_token_budget, reset_daily_usage
from app.core.llm import LLMClient
from app.main import app


@pytest.fixture(autouse=True)
def _reset_budget():
    """每个用例前后清空内存预算与 token 统计（全局状态隔离）。"""
    reset_daily_usage()
    llm_module.reset_usage_stats()
    yield
    reset_daily_usage()
    llm_module.reset_usage_stats()


def test_budget_check_and_add(monkeypatch) -> None:
    """预算校验：未超限放行、累计、超限抛 429。"""
    from fastapi import HTTPException

    monkeypatch.setattr(budget_module.settings, "LLM_DAILY_TOKEN_BUDGET", 100)
    uid = uuid.uuid4()

    check_token_budget(uid)  # 未超限放行
    add_token_usage(uid, 60)
    check_token_budget(uid)  # 60 < 100 放行
    add_token_usage(uid, 50)
    with pytest.raises(HTTPException) as exc:
        check_token_budget(uid)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_chat_rejects_when_budget_exhausted(monkeypatch, authed_headers: dict) -> None:
    """预算耗尽：对话接口在调用 LLM 之前直接 429。"""
    monkeypatch.setattr(budget_module.settings, "LLM_DAILY_TOKEN_BUDGET", 10)
    add_token_usage(uuid.UUID(authed_headers["uid"]), 10)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat", json={"message": "你好"}, headers=authed_headers
        )
    assert resp.status_code == 429


class _UsageFakeCompletions:
    """模拟带 usage 的模型响应。"""

    async def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )


@pytest.mark.asyncio
async def test_chat_accumulates_usage_into_budget(monkeypatch, authed_headers: dict) -> None:
    """对话后本轮 token 增量计入该用户每日预算。"""
    client = LLMClient(api_key="x", base_url="http://localhost:1", model="m")
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=_UsageFakeCompletions()))
    llm_module._llm_semaphore = asyncio.Semaphore(10)
    monkeypatch.setattr(chat_module, "get_llm", lambda: client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        resp = await http_client.post(
            "/api/v1/chat", json={"message": "你好"}, headers=authed_headers
        )
    assert resp.status_code == 200

    entry = budget_module._daily_usage.get(authed_headers["uid"])
    assert entry is not None
    assert entry["tokens"] == 150
