"""MCP server 注册表与适配器注册表（infra）。

- **server 白名单**：只允许 `.env` 中显式声明的 server，`tool` 名显式配置（不猜）；
- **adapter 注册表**：把不同 server 的字段口径映射为领域结构——换/加 server 只动适配器，
  client 与工具层零改动（设计 §15.9/§15.10）；
- **启动自检**：`MCP_ENABLED=true` 时引用了未注册的 adapter 直接拒绝启动
  （参照 `config._reject_default_secret`：配置错误必须在启动时炸，不能等半夜播报才发现）。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# 第三方 server 的工具描述截断长度（防超长文本污染 prompt）
DESCRIPTION_MAX = 200

# 适配器签名：(归一化后的 MCP 返回, 请求的代码/键) -> 领域对象列表
Adapter = Callable[[dict[str, Any], list[str]], list[Any]]


class MCPServerSettings(BaseModel):
    """单个 MCP server 的配置（对应 `MCP_SERVERS` JSON 数组的一项）。"""

    name: str = Field(min_length=1, max_length=64)
    # 拉起命令；留空 = 当前解释器（sys.executable）
    command: str = Field(default="", max_length=512)
    args: list[str] = Field(default_factory=list)
    # 传给子进程的额外环境变量（**高敏**：Key 只走这里，不入库、不进日志）
    env: dict[str, str] = Field(default_factory=dict)
    # 子进程工作目录；缺省 = backend 根目录（保证 `python -m app.xxx` 可导入）
    cwd: str | None = None
    # 要调用的工具名（显式声明，不猜）
    tool: str = Field(min_length=1, max_length=128)
    # 归一化适配器键（注册表内必须存在，否则启动拒绝）
    adapter: str = Field(min_length=1, max_length=64)
    # 单个 server 可独立停用/独立超时（多 server 并存的接缝）
    enabled: bool = True
    timeout_seconds: float | None = Field(default=None, gt=0)
    # 单次调用可接受的返回条目上限（防超量返回）
    max_items: int = Field(default=50, ge=1, le=500)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", v):
            raise ValueError(f"MCP server 名只允许字母/数字/._-：{v!r}")
        return v


_adapters: dict[str, Adapter] = {}


def register_adapter(name: str, fn: Adapter) -> None:
    """注册领域适配器（领域模块在 import 时调用）。"""
    _adapters[name] = fn


def get_adapter(name: str) -> Adapter | None:
    return _adapters.get(name)


def registered_adapters() -> list[str]:
    return sorted(_adapters)


def configured_servers() -> dict[str, MCPServerSettings]:
    """当前配置的 server（按 name 索引）。延迟 import settings 避免循环依赖。"""
    from app.core.config import settings

    return {s.name: s for s in settings.MCP_SERVERS}


def enabled_servers() -> dict[str, MCPServerSettings]:
    return {name: cfg for name, cfg in configured_servers().items() if cfg.enabled}


def get_server(name: str) -> MCPServerSettings | None:
    return configured_servers().get(name)


def validate_configured_servers() -> None:
    """启动自检（lifespan 调用）：命名冲突 / 未注册适配器 → 拒绝启动。"""
    from app.core.config import settings

    # 注意：这里读原始列表而非 `configured_servers()` 的按名索引——
    # 后者会把同名项默默合并，导致重复名检测永远不触发。
    names = [s.name for s in settings.MCP_SERVERS]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        raise ValueError(f"MCP_SERVERS 名称重复：{duplicated}")

    if not settings.MCP_ENABLED:
        return
    if not names:
        logger.warning("MCP_ENABLED=true 但未配置 MCP_SERVERS，外部能力将不可用")
        return
    unknown = sorted(
        {s.adapter for s in settings.MCP_SERVERS if get_adapter(s.adapter) is None}
    )
    if unknown:
        raise ValueError(
            f"MCP_SERVERS 引用了未注册的适配器：{unknown}（已注册：{registered_adapters()}）"
        )


def mask_env(env: dict[str, str]) -> dict[str, str]:
    """只回显键名，**值一律掩码**（server env 是 Key 的常见藏身处）。"""
    return {key: "***" for key in env}


def truncate_description(text: str | None, limit: int = DESCRIPTION_MAX) -> str:
    """第三方 server 的工具描述截断（外部文本不信任长度）。"""
    return (text or "")[:limit]
