"""LangGraph 多 Agent 引擎测试：Fake 模型（不触网），覆盖图结构/路由/工具/流式/引擎切换。

使用 langchain 官方 GenericFakeChatModel（真实 BaseChatModel 回调），
图结构与 astream_events 均为真实 LangGraph 执行路径；仅模型输出为预设。
"""

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.agent.langgraph_engine import LangGraphEngine, _keyword_route, _parse_route
from app.core.config import Settings, settings
from app.core.constants import DEFAULT_USER_ID
from app.models import Todo
from app.tools import registry


class FakeToolChatModel(GenericFakeChatModel):
    """支持 bind_tools 的假模型（返回 self，按预设消息依次响应）。"""

    def bind_tools(self, tools, **kwargs):
        return self


def make_engine(messages: list, max_turns: int = 3) -> LangGraphEngine:
    llm = FakeToolChatModel(messages=iter(messages))
    return LangGraphEngine(llm=llm, registry=registry, max_turns=max_turns)


def _route_msg(route: str) -> AIMessage:
    return AIMessage(content=f'{{"route": "{route}", "reason": "测试"}}')


# ---------- 图结构 ----------


def test_graph_structure() -> None:
    """图包含 supervisor + 3 个子 Agent 节点（+ 系统出入节点）。"""
    engine = make_engine([_route_msg("chat"), AIMessage(content="hi")])
    nodes = set(engine.graph.get_graph().nodes.keys())
    assert {"supervisor", "kb_agent", "tools_agent", "chat_agent"} <= nodes
    assert "__start__" in nodes and "__end__" in nodes


def test_default_engine_is_langgraph() -> None:
    """配置默认引擎为 langgraph（第 5 节约定）。"""
    assert Settings().AGENT_ENGINE == "langgraph"


# ---------- 路由单元 ----------


def test_parse_route() -> None:
    assert _parse_route('{"route": "kb", "reason": "x"}') == "kb"
    assert _parse_route('```json\n{"route": "tools"}\n```') == "tools"
    assert _parse_route("抱歉，我无法判断") is None
    assert _parse_route("") is None


def test_keyword_route() -> None:
    """关键词兜底：工具 > 知识库 > 日常。"""
    assert _keyword_route("帮我创建一个待办：买菜") == "tools"
    assert _keyword_route("我的笔记里有什么") == "kb"
    assert _keyword_route("根据文档总结一下") == "kb"
    assert _keyword_route("你好呀") == "chat"


# ---------- 路由分发 ----------


@pytest.mark.asyncio
async def test_route_to_chat(db_session) -> None:
    """Supervisor 路由到通用 Agent：直接文本回复。"""
    engine = make_engine([_route_msg("chat"), AIMessage(content="你好，我是青木")])
    reply = await engine.run(db_session, DEFAULT_USER_ID, [], "你好")
    assert reply == "你好，我是青木"


@pytest.mark.asyncio
async def test_route_to_kb(db_session) -> None:
    """Supervisor 路由到知识库 Agent：基于检索引用回答（不触发真实检索）。"""
    engine = make_engine(
        [
            _route_msg("kb"),
            AIMessage(content="根据文档《FastAPI 学习笔记》：FastAPI 是异步 Web 框架。"),
        ]
    )
    reply = await engine.run(db_session, DEFAULT_USER_ID, [], "FastAPI 是什么")
    assert "FastAPI" in reply


@pytest.mark.asyncio
async def test_route_to_tools_executes_todo(db_session) -> None:
    """Supervisor 路由到工具 Agent：模型请求工具 → 执行 → 汇报，待办入库。"""
    engine = make_engine(
        [
            _route_msg("tools"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "todo_create",
                        "args": {"title": "买菜"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="好的，已为你创建待办「买菜」"),
        ]
    )
    reply = await engine.run(db_session, DEFAULT_USER_ID, [], "帮我创建一个待办：买菜")
    assert reply == "好的，已为你创建待办「买菜」"

    todos = (await db_session.scalars(select(Todo))).all()
    assert any(t.title == "买菜" for t in todos)


@pytest.mark.asyncio
async def test_keyword_fallback_when_supervisor_garbage(db_session) -> None:
    """Supervisor 输出无法解析 → 关键词兜底路由到工具 Agent。"""
    engine = make_engine(
        [
            AIMessage(content="抱歉，我无法判断这是什么类型"),
            AIMessage(content="已为你创建待办"),
        ]
    )
    reply = await engine.run(db_session, DEFAULT_USER_ID, [], "帮我创建一个待办：买菜")
    assert "待办" in reply


@pytest.mark.asyncio
async def test_max_turns_guard_in_leaf(db_session) -> None:
    """子 Agent 持续请求工具时，达到最大轮数后终止。"""
    tool_calls = [
        AIMessage(
            content="",
            tool_calls=[{"name": "todo_list", "args": {}, "id": f"c{i}", "type": "tool_call"}],
        )
        for i in range(5)
    ]
    engine = make_engine([_route_msg("tools"), *tool_calls], max_turns=2)
    reply = await engine.run(db_session, DEFAULT_USER_ID, [], "继续")
    assert "最大工具调用轮数" in reply


# ---------- 流式 ----------


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


@pytest.mark.asyncio
async def test_run_stream_filters_internal_nodes(db_session, monkeypatch) -> None:
    """run_stream 只产出叶子 Agent 的 token，Supervisor 内部输出被过滤。"""
    engine = make_engine([_route_msg("chat"), AIMessage(content="最终回复")])

    async def fake_events(state, version="v2"):
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "supervisor"},
            "data": {"chunk": _Chunk('{"route": "chat"}')},
        }
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "chat_agent"},
            "data": {"chunk": _Chunk("最终")},
        }
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "chat_agent"},
            "data": {"chunk": _Chunk("回复")},
        }
        yield {"event": "on_chain_end", "metadata": {}, "data": {}}

    monkeypatch.setattr(engine.graph, "astream_events", fake_events)
    parts: list[str] = []
    async for text in engine.run_stream(db_session, DEFAULT_USER_ID, [], "你好"):
        parts.append(text)
    assert "".join(parts) == "最终回复"


@pytest.mark.asyncio
async def test_run_stream_real_graph(db_session) -> None:
    """真实图执行 + 真实 astream_events：叶子节点文本被流式产出。"""
    engine = make_engine([_route_msg("chat"), AIMessage(content="流式回复内容")])
    parts: list[str] = []
    async for text in engine.run_stream(db_session, DEFAULT_USER_ID, [], "你好"):
        parts.append(text)
    assert "".join(parts) == "流式回复内容"


# ---------- 引擎切换 ----------


def test_engine_switch(monkeypatch) -> None:
    """chat._build_agent 按 AGENT_ENGINE 选择引擎：handwritten → Orchestrator。"""
    import app.api.routes.chat as chat_module
    from app.agent.orchestrator import Orchestrator

    monkeypatch.setattr(settings, "AGENT_ENGINE", "handwritten")
    monkeypatch.setattr(chat_module, "get_llm", lambda: object())
    agent = chat_module._build_agent()
    assert isinstance(agent, Orchestrator)


def test_engine_switch_langgraph(monkeypatch) -> None:
    """AGENT_ENGINE=langgraph → LangGraphEngine（类可被替换注入，无需真实模型）。"""
    import app.api.routes.chat as chat_module

    monkeypatch.setattr(settings, "AGENT_ENGINE", "langgraph")

    class _Stub:
        def __init__(self, registry=None) -> None:
            self.registry = registry

    monkeypatch.setattr("app.agent.langgraph_engine.LangGraphEngine", _Stub)
    agent = chat_module._build_agent()
    assert isinstance(agent, _Stub)


# ---------- 轨迹（trajectory） ----------


def _enable_trace(monkeypatch) -> None:
    """conftest 默认关闭轨迹，需要轨迹的用例自行打开（顺带证明开关生效）。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", True)


@pytest.mark.asyncio
async def test_trajectory_records_route_node_and_answer(monkeypatch, db_session) -> None:
    """路由 → 节点 → 回复：可复原路由判定来源与选中的子 Agent。"""
    _enable_trace(monkeypatch)
    engine = make_engine([_route_msg("chat"), AIMessage(content="你好")])
    await engine.run(db_session, DEFAULT_USER_ID, [], "你好")

    traj = engine.last_trajectory
    assert traj["engine"] == "langgraph"
    assert traj["truncated"] is False
    assert [s["type"] for s in traj["steps"]] == ["route", "node", "answer"]
    route = traj["steps"][0]
    assert route["route"] == "chat"
    assert route["source"] == "llm"
    assert route["ms"] >= 0
    assert traj["steps"][1]["node"] == "chat_agent"
    assert traj["steps"][2]["chars"] == len("你好")


@pytest.mark.asyncio
async def test_trajectory_route_source_keyword_on_bad_llm_output(monkeypatch, db_session) -> None:
    """Supervisor 输出不可解析 → 关键词兜底，轨迹如实标注 source=keyword。"""
    _enable_trace(monkeypatch)
    engine = make_engine([AIMessage(content="我无法判断"), AIMessage(content="好的")])
    await engine.run(db_session, DEFAULT_USER_ID, [], "我的笔记里有什么")

    route = engine.last_trajectory["steps"][0]
    assert route["route"] == "kb"
    assert route["source"] == "keyword"


@pytest.mark.asyncio
async def test_trajectory_records_tool_step(monkeypatch, db_session) -> None:
    """工具调用与结果进轨迹（含耗时与状态）。"""
    _enable_trace(monkeypatch)
    engine = make_engine(
        [
            _route_msg("tools"),
            AIMessage(content="", tool_calls=[{"name": "kb_search", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="完成"),
        ]
    )
    await engine.run(db_session, DEFAULT_USER_ID, [], "检索一下")

    steps = engine.last_trajectory["steps"]
    tool = next(s for s in steps if s["type"] == "tool")
    assert tool["name"] == "kb_search"
    assert tool["status"] == "ok"
    assert tool["arguments"] == '{"query": "x"}'
    assert tool["ms"] >= 0
    assert tool["result"]


@pytest.mark.asyncio
async def test_trajectory_disabled_returns_empty(monkeypatch, db_session) -> None:
    """开关关闭：不记录（AGENTS §8）。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", False)
    engine = make_engine([_route_msg("chat"), AIMessage(content="你好")])
    await engine.run(db_session, DEFAULT_USER_ID, [], "你好")
    assert engine.last_trajectory == {}


@pytest.mark.asyncio
async def test_trajectory_no_secret_leak(monkeypatch, db_session) -> None:
    """轨迹禁落密钥（AGENTS §6/§15 硬红线）。"""
    _enable_trace(monkeypatch)
    engine = make_engine(
        [
            _route_msg("tools"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "kb_search", "args": {"query": "x", "api_key": "sk-leak-me"}, "id": "c1"}
                ],
            ),
            AIMessage(content="完成"),
        ]
    )
    await engine.run(db_session, DEFAULT_USER_ID, [], "检索一下")

    blob = json.dumps(engine.last_trajectory, ensure_ascii=False)
    assert "sk-leak-me" not in blob


@pytest.mark.asyncio
async def test_stream_records_trajectory(monkeypatch, db_session) -> None:
    """流式路径同样产出轨迹（回复长度=产出字符数）。"""
    _enable_trace(monkeypatch)
    engine = make_engine([_route_msg("chat"), AIMessage(content="流式回复")])
    parts = [chunk async for chunk in engine.run_stream(db_session, DEFAULT_USER_ID, [], "你好")]

    traj = engine.last_trajectory
    assert [s["type"] for s in traj["steps"]] == ["route", "node", "answer"]
    assert traj["steps"][2]["chars"] == len("".join(parts))
