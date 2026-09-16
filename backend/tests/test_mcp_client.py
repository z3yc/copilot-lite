"""通用 MCP client：真 stdio 协议（stub 子进程）+ 超时/重连/降级/脱敏/跨域复用。"""

import sys

import pytest

from app.core.config import settings
from app.mcp.client import MCPError, call_configured, close_mcp_clients
from app.mcp.registry import MCPServerSettings


def _server(
    name: str = "fund-quotes",
    *,
    module: str = "tests.support.stub_mcp_server",
    tool: str = "get_fund_nav",
    mode: str = "ok",
    enabled: bool = True,
    timeout: float | None = None,
    extra_env: dict[str, str] | None = None,
) -> MCPServerSettings:
    return MCPServerSettings(
        name=name,
        command=sys.executable,
        args=["-m", module],
        env={"STUB_MODE": mode, **(extra_env or {})},
        tool=tool,
        adapter="fund_nav_v1",
        enabled=enabled,
        timeout_seconds=timeout,
    )


def _configure(monkeypatch, *servers: MCPServerSettings) -> None:
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_CALL_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(settings, "MCP_SERVERS", list(servers))


async def test_call_returns_structured_result(monkeypatch) -> None:
    _configure(monkeypatch, _server())
    out = await call_configured("fund-quotes", {"codes": ["000001"]})
    assert out["server"] == "fund-quotes"
    assert out["is_error"] is False
    assert out["structured"]["quotes"][0]["code"] == "000001"
    assert out["structured"]["missing"] == []


async def test_client_is_domain_agnostic(monkeypatch) -> None:
    """接缝回归：**非基金域**的 server 不改 client 一行即可调用（设计 §15.9）。"""
    _configure(
        monkeypatch,
        _server(),
        _server(
            "generic-echo",
            module="tests.support.stub_generic_server",
            tool="echo",
            mode="ok",
        ),
    )
    fund = await call_configured("fund-quotes", {"codes": ["000001"]})
    echo = await call_configured("generic-echo", {"text": "hi"})
    # stub 发的是字符串净值：**口径差异由适配层吸收**（Task 5 专测），client 只搬运
    assert fund["structured"]["quotes"][0]["nav"] == "1.2500"
    assert echo["structured"] == {"echo": "hi"}


async def test_disabled_master_switch_raises_readable_error(monkeypatch) -> None:
    _configure(monkeypatch, _server())
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    with pytest.raises(MCPError, match="MCP 未启用"):
        await call_configured("fund-quotes", {"codes": ["000001"]})


async def test_unknown_server_raises(monkeypatch) -> None:
    _configure(monkeypatch, _server())
    with pytest.raises(MCPError, match="未配置 MCP server"):
        await call_configured("nope", {})


async def test_per_server_disable_is_honoured(monkeypatch) -> None:
    _configure(monkeypatch, _server(enabled=False))
    with pytest.raises(MCPError, match="未配置 MCP server"):
        await call_configured("fund-quotes", {"codes": ["000001"]})


async def test_crash_on_start_raises_and_does_not_hang(monkeypatch) -> None:
    _configure(monkeypatch, _server(mode="crash"))
    with pytest.raises(MCPError, match="启动失败"):
        await call_configured("fund-quotes", {"codes": ["000001"]})


async def test_timeout_drops_session_and_next_call_reconnects(monkeypatch) -> None:
    """超时必须**丢弃会话**：被取消的 stdio 调用不可复用（R3 流式教训的同款坑）。"""
    _configure(monkeypatch, _server(mode="slow", timeout=0.4))
    with pytest.raises(MCPError, match="调用超时"):
        await call_configured("fund-quotes", {"codes": ["000001"]})

    # 换成正常模式（新子进程读到的 STUB_MODE 变了）→ 证明句柄已丢弃、会自动重连
    monkeypatch.setattr(settings, "MCP_SERVERS", [_server(mode="ok", timeout=10.0)])
    out = await call_configured("fund-quotes", {"codes": ["000001"]})
    assert out["structured"]["quotes"][0]["code"] == "000001"


async def test_missing_codes_are_reported_not_fabricated(monkeypatch) -> None:
    _configure(monkeypatch, _server(mode="missing"))
    out = await call_configured("fund-quotes", {"codes": ["000001"]})
    assert out["structured"] == {"quotes": [], "missing": ["000001"]}


async def test_env_secret_never_reaches_logs(monkeypatch, caplog) -> None:
    _configure(monkeypatch, _server(extra_env={"FUND_API_KEY": "sk-never-log-me"}))
    with caplog.at_level("DEBUG"):
        await call_configured("fund-quotes", {"codes": ["000001"]})
    assert "sk-never-log-me" not in caplog.text


async def test_warns_when_configured_tool_absent(monkeypatch, caplog) -> None:
    _configure(monkeypatch, _server(tool="not_a_real_tool"))
    with caplog.at_level("WARNING"):
        result = await call_configured("fund-quotes", {"codes": ["000001"]})
    assert "未提供配置的工具" in caplog.text
    assert result["is_error"] is True  # server 侧报「未知工具」，如实上抛不吞


async def test_reset_and_close_are_safe_when_nothing_started() -> None:
    await close_mcp_clients()  # 不抛
