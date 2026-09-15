"""trajectory 记录器测试：步序、规范化上限、脱敏、开关。"""

import json

from app.agent.trajectory import (
    TRAJECTORY_ARG_MAX,
    TRAJECTORY_MAX_BYTES,
    TRAJECTORY_MAX_STEPS,
    TRAJECTORY_RESULT_MAX,
    TrajectoryRecorder,
    redact_json_args,
)


def test_trace_disabled_in_test_env() -> None:
    """conftest 把轨迹开关默认关掉（AGENTS §8：后台/可选能力测试环境默认关）。"""
    from app.core.config import settings

    assert settings.AGENT_TRACE_ENABLED is False


def test_disabled_recorder_returns_empty() -> None:
    """关闭开关：不记录，build() 返回空 dict（前端据此不显示面板）。"""
    rec = TrajectoryRecorder("langgraph", enabled=False)
    rec.route("kb", "llm", 10)
    rec.node("kb_agent")
    rec.tool("kb_search", '{"query": "x"}', "结果")
    rec.answer(3)
    assert rec.build() == {}


def test_records_steps_in_order() -> None:
    rec = TrajectoryRecorder("langgraph")
    rec.route("tools", "llm", 12)
    rec.node("tools_agent")
    rec.tool("kb_search", '{"query": "x"}', "结果A", ms=7)
    rec.answer(9)

    built = rec.build()
    assert built["engine"] == "langgraph"
    assert built["truncated"] is False
    assert built["total_ms"] >= 0
    assert [s["type"] for s in built["steps"]] == ["route", "node", "tool", "answer"]
    assert built["steps"][0] == {"type": "route", "route": "tools", "source": "llm", "ms": 12}
    tool = built["steps"][2]
    assert tool["name"] == "kb_search"
    assert tool["status"] == "ok"
    assert tool["ms"] == 7
    assert tool["result"] == "结果A"


def test_steps_capped_and_marked_truncated() -> None:
    rec = TrajectoryRecorder("langgraph")
    for i in range(TRAJECTORY_MAX_STEPS + 5):
        rec.tool(f"t{i}", "{}", "r")
    built = rec.build()
    assert len(built["steps"]) == TRAJECTORY_MAX_STEPS
    assert built["truncated"] is True


def test_arg_and_result_clipped() -> None:
    rec = TrajectoryRecorder("langgraph")
    rec.tool("t", json.dumps({"q": "长" * 1000}, ensure_ascii=False), "结" * 2000)
    step = rec.build()["steps"][0]
    assert len(step["arguments"]) == TRAJECTORY_ARG_MAX
    assert len(step["result"]) == TRAJECTORY_RESULT_MAX


def test_sensitive_keys_are_masked() -> None:
    """密钥不入轨迹（AGENTS §6/§15 硬红线）。"""
    rec = TrajectoryRecorder("langgraph")
    rec.tool("t", '{"api_key": "sk-secret-123", "query": "ok"}', "r")
    args = rec.build()["steps"][0]["arguments"]
    assert "sk-secret-123" not in args
    assert "***" in args
    assert "ok" in args


def test_redact_json_args_keeps_non_sensitive_untouched() -> None:
    """无敏感 key 时原样返回（不改写格式）。"""
    raw = '{ "query" : "x" }'
    assert redact_json_args(raw) == raw


def test_redact_does_not_touch_token_lookalike() -> None:
    """max_tokens 不是密钥（防误伤）；refresh_token 是。"""
    out = redact_json_args('{"max_tokens": 128, "refresh_token": "abc"}')
    assert '"max_tokens": 128' in out
    assert "abc" not in out


def test_total_bytes_capped() -> None:
    """总字节上限：整步丢弃到装得下为止。"""
    rec = TrajectoryRecorder("langgraph")
    for i in range(TRAJECTORY_MAX_STEPS):
        rec.tool(f"tool-{i}", "{}", "结" * TRAJECTORY_RESULT_MAX)
    built = rec.build()
    size = len(json.dumps(built, ensure_ascii=False).encode("utf-8"))
    assert size <= TRAJECTORY_MAX_BYTES
    assert built["truncated"] is True


def test_reset_clears_steps() -> None:
    rec = TrajectoryRecorder("langgraph")
    rec.node("kb_agent")
    rec.reset()
    assert rec.build() == {}
