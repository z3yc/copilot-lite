"""工具轮的模型独白不得当作回答产出（两个引擎同测）。

回归对象：模型在 tool_calls 那一轮同时输出 content（如 "I'll search …"），
被 run_stream 原样转发/落库，回答变成「英文独白 + 真答案」。
"""

import json
import re
from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from app.agent.langgraph_engine import LangGraphEngine
from app.agent.orchestrator import Orchestrator
from app.core.config import settings
from app.core.constants import DEFAULT_USER_ID
from app.core.llm import ToolCall
from app.tools import registry
from tests.test_orchestrator import _SC, _SD, StreamFakeLLM, _Stream


class _FakeToolChatModel(GenericFakeChatModel):
    """`bind_tools` + **流式也产出 tool_calls** 的假模型。

    基类 `GenericFakeChatModel._stream` 只切分 content 与 additional_kwargs，
    会把 `AIMessage.tool_calls` 整体丢掉；真实模型（DeepSeek / ChatOpenAI）是
    逐 delta 下发 tool_calls 的，丢掉就构造不出「同轮既有 content 又有 tool_calls」
    这个回归场景。这里最小补上该行为（事件回调照发，astream_events 才看得到）。
    """

    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = next(self.messages)
        msg = AIMessage(content=message) if isinstance(message, str) else message
        content = msg.content or ""
        if content:
            pieces = re.split(r"(\s)", content)
            for idx, token in enumerate(pieces):
                chunk = ChatGenerationChunk(message=AIMessageChunk(content=token, id=msg.id))
                if idx == len(pieces) - 1:
                    chunk.message.chunk_position = "last"
                if run_manager:
                    run_manager.on_llm_new_token(token, chunk=chunk)
                yield chunk
        for i, tc in enumerate(msg.tool_calls or []):
            chunk = ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    id=msg.id,
                    tool_call_chunks=[
                        {
                            "name": tc["name"],
                            "args": json.dumps(tc["args"], ensure_ascii=False),
                            "id": tc["id"],
                            "index": i,
                        }
                    ],
                )
            )
            if run_manager:
                run_manager.on_llm_new_token("", chunk=chunk)
            yield chunk


def _route_msg(route: str) -> AIMessage:
    return AIMessage(content=f'{{"route": "{route}", "reason": "测试"}}')


# ---------- LangGraph ----------


@pytest.mark.asyncio
async def test_langgraph_stream_drops_tool_round_narration(db_session, monkeypatch) -> None:
    """第一轮带 tool_calls 且 content 是独白 → 独白不得出现；只产出最终答案。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", True)
    llm = _FakeToolChatModel(
        messages=iter(
            [
                _route_msg("tools"),
                AIMessage(
                    content="I'll check your todo list for you.",
                    tool_calls=[{"name": "todo_list", "args": {}, "id": "c1"}],
                ),
                AIMessage(content="你的待办是空的。"),
            ]
        )
    )
    engine = LangGraphEngine(llm=llm, registry=registry, max_turns=3)
    parts = [p async for p in engine.run_stream(db_session, DEFAULT_USER_ID, [], "看下待办")]

    text = "".join(parts)
    assert text == "你的待办是空的。", f"独白泄漏：{text!r}"
    # 轨迹长度只统计真正给用户的内容（独白轮不计入）
    assert engine.last_trajectory["steps"][-1]["chars"] == len(text)


@pytest.mark.asyncio
async def test_langgraph_stream_keeps_plain_chat_progressive(db_session) -> None:
    """不挂工具的 chat_agent：仍逐字产出（缓冲对这类轮次无收益，不应牺牲流式）。"""
    llm = _FakeToolChatModel(
        messages=iter([_route_msg("chat"), AIMessage(content="你好 呀 你好")])
    )
    engine = LangGraphEngine(llm=llm, registry=registry, max_turns=3)
    parts = [p async for p in engine.run_stream(db_session, DEFAULT_USER_ID, [], "你好")]

    assert "".join(parts) == "你好 呀 你好"
    assert len(parts) > 1, f"chat_agent 丢了 token 级流式：{parts!r}"


# ---------- 手写 Orchestrator ----------


class _NarratingStreamLLM(StreamFakeLLM):
    """在既有 StreamFakeLLM 上补一种轮次：同轮既有 content 又有 tool_calls。

    既有 fake 的轮次形状是 `("text", str)` / `("tool", [ToolCall, ...])`，
    表达不了「模型边说话边调工具」——这正是被 DeepSeek 打破互斥假设的真实行为。
    """

    async def stream_raw(self, messages, tools=None, temperature=0.7):
        kind, *payload = self.rounds[0]
        if kind != "narrating_tool":
            return await super().stream_raw(messages, tools=tools, temperature=temperature)
        self.rounds.pop(0)
        text, calls = payload
        chunks = [_SC(_SD(content=piece)) for piece in re.split(r"(\s)", text) if piece]
        for i, tc in enumerate(calls):
            fn = SimpleNamespace(name=tc.name, arguments=tc.arguments)
            chunks.append(
                _SC(_SD(tool_calls=[SimpleNamespace(index=i, id=tc.id, function=fn)]))
            )
        return _Stream(chunks)


@pytest.mark.asyncio
async def test_orchestrator_stream_drops_tool_round_narration(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", True)
    llm = _NarratingStreamLLM(
        [
            (
                "narrating_tool",
                "I'll look that up for you.",
                [ToolCall(id="c1", name="todo_list", arguments="{}")],
            ),
            ("text", "你的待办是空的。"),
        ]
    )
    orch = Orchestrator(llm=llm, registry=registry, max_turns=3)
    parts = [p async for p in orch.run_stream(db_session, DEFAULT_USER_ID, [], "看下待办")]

    text = "".join(parts)
    assert text == "你的待办是空的。", f"独白泄漏：{text!r}"
    # 轨迹长度只统计真正给用户的内容（独白轮不计入）
    assert orch.last_trajectory["steps"][-1]["chars"] == len(text)
