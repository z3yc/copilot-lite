"""对话编排器（ReAct 循环）测试：使用 FakeLLM 模拟模型响应。"""

import pytest

from app.agent.orchestrator import Orchestrator
from app.core.config import settings
from app.core.constants import DEFAULT_USER_ID
from app.core.llm import ChatResult, ToolCall
from app.tools import registry


class FakeLLM:
    """按预设顺序返回响应的假模型。"""

    def __init__(self, responses: list[ChatResult]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    async def chat(self, messages, tools=None, temperature=0.7, response_format=None) -> ChatResult:
        self.requests.append({"messages": messages, "tools": tools})
        return self.responses.pop(0)

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_react_loop_with_tool_call(db_session) -> None:
    """模型先请求调用工具，拿到结果后再给出最终回复。"""
    fake = FakeLLM(
        [
            ChatResult(
                tool_calls=[
                    ToolCall(id="call_1", name="todo_create", arguments='{"title": "买菜"}')
                ]
            ),
            ChatResult(content="好的，已为你创建待办「买菜」"),
        ]
    )
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    reply = await orch.run(
        session=db_session,
        user_id=DEFAULT_USER_ID,
        history=[],
        user_message="帮我创建一个待办：买菜",
    )

    assert reply == "好的，已为你创建待办「买菜」"

    # 第一次请求应携带工具定义
    assert fake.requests[0]["tools"] is not None
    tool_names = [t["function"]["name"] for t in fake.requests[0]["tools"]]
    assert "todo_create" in tool_names

    # 第二轮请求中应包含 assistant tool_calls 与 tool 结果回填
    second = fake.requests[1]["messages"]
    roles = [m["role"] for m in second]
    assert "assistant" in roles and "tool" in roles


@pytest.mark.asyncio
async def test_direct_reply_without_tools(db_session) -> None:
    """无工具调用时直接返回文本。"""
    fake = FakeLLM([ChatResult(content="你好！有什么可以帮你？")])
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    reply = await orch.run(db_session, DEFAULT_USER_ID, [], "你好")
    assert reply == "你好！有什么可以帮你？"


@pytest.mark.asyncio
async def test_max_turns_guard(db_session) -> None:
    """模型持续请求工具时，达到最大轮数后终止。"""
    fake = FakeLLM(
        [
            ChatResult(tool_calls=[ToolCall(id=f"c{i}", name="todo_list", arguments="{}")])
            for i in range(10)
        ]
    )
    orch = Orchestrator(llm=fake, registry=registry, max_turns=2)
    reply = await orch.run(db_session, DEFAULT_USER_ID, [], "继续")
    assert "最大工具调用轮数" in reply


@pytest.mark.asyncio
async def test_history_window_keeps_system_context(db_session, monkeypatch) -> None:
    """窗口截断只作用于对话历史；system 上下文（附件/记忆）常驻不被截掉。"""
    fake = FakeLLM([ChatResult(content="ok")])
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    history = [{"role": "system", "content": "【附件】独特内容XYZ"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"消息{i}"}
        for i in range(60)
    ]
    monkeypatch.setattr("app.agent.orchestrator.settings.HISTORY_WINDOW", 10)
    await orch.run(db_session, DEFAULT_USER_ID, history, "继续")

    messages = fake.requests[0]["messages"]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert any("独特内容XYZ" in m["content"] for m in system_msgs), (
        "system 上下文不能被窗口截掉"
    )
    convo = [m for m in messages if m["role"] in ("user", "assistant")]
    assert len(convo) == 11  # 窗口 10 + 本轮新消息
    assert convo[0]["content"] == "消息50"  # 最老的 50 条被滚动截断


# ---------------- 流式编排（run_stream） ----------------

from types import SimpleNamespace


class _SD:
    """模拟流式 delta：content 或 tool_calls。"""

    def __init__(self, content: str | None = None, tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _SC:
    def __init__(self, delta: _SD) -> None:
        self.choices = [SimpleNamespace(delta=delta)]


class _Stream:
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


class StreamFakeLLM:
    """流式假模型：rounds 为 [("text", str) | ("tool", ToolCall...), ...]。"""

    def __init__(self, rounds: list) -> None:
        self.rounds = list(rounds)

    async def stream_raw(self, messages, tools=None, temperature=0.7):
        kind, payload = self.rounds.pop(0)
        if kind == "text":
            text = payload
            return _Stream([_SC(_SD(text[i : i + 3])) for i in range(0, len(text), 3)])
        # 工具轮：模拟 tool_calls delta
        chunks = []
        for tc in payload:
            fn = SimpleNamespace(name=tc.name, arguments=tc.arguments)
            tc_delta = SimpleNamespace(index=0, id=tc.id, function=fn)
            chunks.append(_SC(_SD(tool_calls=[tc_delta])))
        return _Stream(chunks)

    async def chat(self, messages, tools=None, temperature=0.7, response_format=None):
        raise AssertionError("流式测试不应调用非流式 chat")

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_run_stream_with_tool_and_text(db_session) -> None:
    """流式循环：先工具轮（todo_create），后文本轮，逐 token 产出。"""
    fake = StreamFakeLLM(
        [
            ("tool", [ToolCall(id="s1", name="todo_create", arguments='{"title": "流式任务"}')]),
            ("text", "好的，已创建流式任务"),
        ]
    )
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    parts: list[str] = []
    async for text in orch.run_stream(db_session, DEFAULT_USER_ID, [], "创建任务"):
        parts.append(text)

    assert "".join(parts) == "好的，已创建流式任务"

    # 工具已实际执行（todo_create 入库）
    from sqlalchemy import select

    from app.models import Todo

    todos = (await db_session.scalars(select(Todo))).all()
    assert any(t.title == "流式任务" for t in todos)


@pytest.mark.asyncio
async def test_run_stream_pure_text(db_session) -> None:
    """纯文本轮：直接流式产出。"""
    fake = StreamFakeLLM([("text", "你好，我是青木")])
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    parts: list[str] = []
    async for text in orch.run_stream(db_session, DEFAULT_USER_ID, [], "你好"):
        parts.append(text)

    assert "".join(parts) == "你好，我是青木"


# ---------------- 轨迹（trajectory） ----------------


def _enable_trace(monkeypatch) -> None:
    """conftest 默认关闭轨迹，需要轨迹的用例自行打开。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", True)


@pytest.mark.asyncio
async def test_trajectory_records_node_and_answer(monkeypatch, db_session) -> None:
    """手写引擎：节点=orchestrator，无 route step（它没有路由能力）。"""
    _enable_trace(monkeypatch)
    fake = FakeLLM([ChatResult(content="你好！有什么可以帮你？")])
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)
    await orch.run(db_session, DEFAULT_USER_ID, [], "你好")

    traj = orch.last_trajectory
    assert traj["engine"] == "handwritten"
    assert traj["truncated"] is False
    assert [s["type"] for s in traj["steps"]] == ["node", "answer"]
    assert traj["steps"][0]["node"] == "orchestrator"
    assert traj["steps"][1]["chars"] == len("你好！有什么可以帮你？")


@pytest.mark.asyncio
async def test_trajectory_records_tool_step(monkeypatch, db_session) -> None:
    """工具调用与结果进轨迹（含耗时与状态）。"""
    _enable_trace(monkeypatch)
    fake = FakeLLM(
        [
            ChatResult(tool_calls=[ToolCall(id="call_1", name="todo_list", arguments="{}")]),
            ChatResult(content="这是你的待办"),
        ]
    )
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)
    await orch.run(db_session, DEFAULT_USER_ID, [], "看看我的待办")

    tool = next(s for s in orch.last_trajectory["steps"] if s["type"] == "tool")
    assert tool["name"] == "todo_list"
    assert tool["status"] == "ok"
    assert tool["ms"] >= 0
    assert [s["type"] for s in orch.last_trajectory["steps"]] == [
        "node",
        "tool",
        "answer",
    ]


@pytest.mark.asyncio
async def test_trajectory_disabled_returns_empty(monkeypatch, db_session) -> None:
    """开关关闭：不记录（AGENTS §8）。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", False)
    fake = FakeLLM([ChatResult(content="你好")])
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)
    await orch.run(db_session, DEFAULT_USER_ID, [], "你好")
    assert orch.last_trajectory == {}


@pytest.mark.asyncio
async def test_stream_records_trajectory(monkeypatch, db_session) -> None:
    """run_stream 的每个出口都收尾轨迹（防某个 return 分支漏记）。"""
    _enable_trace(monkeypatch)
    fake = StreamFakeLLM([("text", "你好！有什么可以帮你？")])
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    parts = [p async for p in orch.run_stream(db_session, DEFAULT_USER_ID, [], "你好")]
    traj = orch.last_trajectory
    assert [s["type"] for s in traj["steps"]] == ["node", "answer"]
    assert traj["steps"][1]["chars"] == len("".join(parts))
