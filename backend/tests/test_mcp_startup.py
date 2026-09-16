"""lifespan 启动自检接线：配置错误必须在启动时炸，而不是运行到半夜才炸。"""

import pytest

from app.core.config import settings
from app.main import app, lifespan
from app.mcp.registry import MCPServerSettings, register_adapter


async def test_lifespan_starts_with_valid_server_config(monkeypatch) -> None:
    register_adapter("t1_startup_probe", lambda payload, codes: [])
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "MCP_SERVERS",
        [
            MCPServerSettings(
                name="probe", command="", tool="t", adapter="t1_startup_probe"
            )
        ],
    )
    async with lifespan(app):
        pass  # 能进能出即通过（自检未抛异常）


async def test_lifespan_rejects_unknown_adapter(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "MCP_SERVERS",
        [MCPServerSettings(name="probe", command="", tool="t", adapter="没注册")],
    )
    with pytest.raises(ValueError, match="未注册的适配器"):
        async with lifespan(app):
            pass
