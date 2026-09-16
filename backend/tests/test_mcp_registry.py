"""MCP server 配置模型 / 白名单 / 适配器注册表 / 掩码与截断。"""

import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.mcp import registry


def _cfg(**kw):
    base = {
        "name": "fund-quotes",
        "command": "",
        "args": ["-m", "app.mcp_servers.fund_quotes"],
        "tool": "get_fund_nav",
        "adapter": "fund_nav_v1",
    }
    base.update(kw)
    return registry.MCPServerSettings(**base)


def test_settings_parses_servers_from_json_env(monkeypatch) -> None:
    """MCP_SERVERS 走 .env 的 JSON 字符串（三件套里的实际形态）。"""
    raw = json.dumps([_cfg().model_dump()])
    monkeypatch.setenv("MCP_SERVERS", raw)
    parsed = Settings(_env_file=None)
    assert [s.name for s in parsed.MCP_SERVERS] == ["fund-quotes"]
    assert parsed.MCP_SERVERS[0].tool == "get_fund_nav"
    assert parsed.MCP_SERVERS[0].adapter == "fund_nav_v1"


def test_server_name_must_be_slug() -> None:
    with pytest.raises(ValidationError):
        _cfg(name="基金 行情")


def test_mask_env_never_returns_values() -> None:
    masked = registry.mask_env({"FUND_API_KEY": "sk-real", "OTHER": "x"})
    assert masked == {"FUND_API_KEY": "***", "OTHER": "***"}


def test_truncate_description_caps_length() -> None:
    assert len(registry.truncate_description("字" * 500)) == registry.DESCRIPTION_MAX
    assert registry.truncate_description(None) == ""


def test_duplicate_server_names_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SERVERS", [_cfg(), _cfg()])
    with pytest.raises(ValueError, match="名称重复"):
        registry.validate_configured_servers()


def test_unknown_adapter_rejected_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SERVERS", [_cfg(adapter="不存在的适配器")])
    with pytest.raises(ValueError, match="未注册的适配器"):
        registry.validate_configured_servers()


def test_enabled_without_servers_only_warns(monkeypatch, caplog) -> None:
    """开了总开关但没配 server：**降级不炸**（设计 §8）。"""
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SERVERS", [])
    with caplog.at_level("WARNING"):
        registry.validate_configured_servers()
    assert "未配置 MCP_SERVERS" in caplog.text


def test_disabled_skips_adapter_check(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_SERVERS", [_cfg(adapter="随便写")])
    registry.validate_configured_servers()  # 不抛


def test_adapter_registry_roundtrip() -> None:
    def _adapter(payload, codes):
        return []

    registry.register_adapter("t1_probe", _adapter)
    assert registry.get_adapter("t1_probe") is _adapter
    assert "t1_probe" in registry.registered_adapters()
    assert registry.get_adapter("nope") is None


def test_enabled_servers_filters_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        settings, "MCP_SERVERS", [_cfg(), _cfg(name="other", enabled=False)]
    )
    assert set(registry.enabled_servers()) == {"fund-quotes"}
    assert registry.get_server("fund-quotes").tool == "get_fund_nav"
    assert registry.get_server("missing") is None
