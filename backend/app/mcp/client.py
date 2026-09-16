"""MCP stdio 客户端：句柄生命周期（本文件在 Task 4 补全真正的协议实现）。

Task 1 只需要「可被 lifespan/conftest 调用」的最小表面：
- `MCPError`：统一异常类型（领域工具据此转可读提示）；
- `reset_mcp_clients()` / `close_mcp_clients()`：测试隔离与应用关停；
- `call_configured()`：Task 4 实现（拉起子进程 → initialize → tools/call）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MCPError(RuntimeError):
    """MCP 调用失败（未配置/超时/协议错误），上层转可读提示。"""


# 模块级可变状态（AGENTS §8：必须可重置）
_handles: dict[str, Any] = {}


def reset_mcp_clients() -> None:
    """清空句柄表（测试隔离用）；**不关进程**——生产关停请用 `close_mcp_clients()`。"""
    _handles.clear()


async def close_mcp_clients() -> None:
    """关闭全部 server 子进程（应用 shutdown / 测试收尾）。"""
    for name in list(_handles):
        _handles.pop(name, None)
        logger.debug("关闭 MCP 会话（占位实现）: name=%s", name)
