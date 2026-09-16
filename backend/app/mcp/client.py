"""通用 MCP stdio 客户端（infra 层，**不感知任何领域**）。

契约：`call_configured(server_name, arguments)`——server 名与工具名都来自 `.env`
的 `MCP_SERVERS`（管理员级白名单）。本模块对「基金」一无所知；接入新 MCP 只需
「加配置 + 写适配器」（见 `app/mcp/__init__.py` 的四步清单）。

生命周期（设计 §5.2/§15.10）：
- **懒启动**：首次调用拉起 stdio 子进程 → `initialize` → 缓存 `tools/list`；
- **常驻复用**：不随请求启停；单 server 一把锁（stdio 会话非并发安全）；
- **失败即丢弃会话（含超时）**：被取消的 `call_tool` 不能复用——同 R3 流式心跳的
  教训（取消会把底层流搅坏），所以超时/异常一律 `_drop`，下次调用自动重连；
- **降级不炸**：`MCP_ENABLED=false` / 未配置 / 单 server `enabled=false` → 抛 `MCPError`，
  由领域工具转成可读提示（AGENTS §10 失败回退优先可用性）。

安全：日志只打 server 名/工具名/异常类型；`env` 值永不打印（AGENTS §6.1/§6.8）。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

from app.core.config import settings
from app.mcp.registry import get_server, truncate_description

logger = logging.getLogger(__name__)

# 丢弃会话时的关闭超时（防清理动作本身挂住请求路径）
_CLOSE_TIMEOUT_SECONDS = 5.0


class MCPError(RuntimeError):
    """MCP 调用失败（未配置/超时/协议错误），上层转可读提示。"""


@dataclass
class _ServerHandle:
    """一个已就绪的 server 会话。"""

    name: str
    stack: AsyncExitStack
    session: ClientSession
    # 工具名 → 截断后的描述（供将来工具披露/白名单使用）
    tools: dict[str, str] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# 模块级可变状态（AGENTS §8：必须可重置）
_handles: dict[str, _ServerHandle] = {}
_start_lock: asyncio.Lock | None = None


def _get_start_lock() -> asyncio.Lock:
    global _start_lock
    if _start_lock is None:
        _start_lock = asyncio.Lock()
    return _start_lock


def reset_mcp_clients() -> None:
    """清空句柄表（测试隔离用）；**不关进程**——生产关停请用 `close_mcp_clients()`。"""
    _handles.clear()


def _backend_dir() -> str:
    """backend 根目录：作为子进程默认 cwd（保证 `python -m app.xxx` 可导入）。"""
    return str(Path(__file__).resolve().parents[2])


async def _drop(name: str, *, reason: str) -> None:
    """丢弃会话（下次调用自动重连）；关闭失败只记 debug，不让清理掩盖真实错误。"""
    handle = _handles.pop(name, None)
    if handle is None:
        return
    logger.info("已丢弃 MCP 会话: name=%s reason=%s", name, reason)
    try:
        await asyncio.wait_for(handle.stack.aclose(), timeout=_CLOSE_TIMEOUT_SECONDS)
    except Exception:
        logger.debug("关闭 MCP 会话失败（忽略）: name=%s", name, exc_info=True)


async def _start(name: str) -> _ServerHandle:
    """拉起子进程并完成 `initialize` 与 `tools/list`。"""
    cfg = get_server(name)
    if cfg is None:
        raise MCPError(f"未配置 MCP server：{name}")
    params = StdioServerParameters(
        # 留空 = 当前解释器（避开 Windows `python` 商店桩）
        command=cfg.command or sys.executable,
        args=list(cfg.args),
        # env 显式给出时才覆盖：与 SDK 的安全默认环境合并，带上自定义 Key
        env={**get_default_environment(), **cfg.env} if cfg.env else None,
        cwd=cfg.cwd or _backend_dir(),
    )
    stack = AsyncExitStack()
    try:
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listed = await session.list_tools()
    except Exception as exc:
        with suppress(Exception):
            await stack.aclose()
        logger.warning("MCP server 启动失败: name=%s type=%s", name, type(exc).__name__)
        raise MCPError(f"MCP server 启动失败：{name}") from exc

    tools = {
        tool.name: truncate_description(getattr(tool, "description", None))
        for tool in listed.tools
    }
    if cfg.tool not in tools:
        logger.warning(
            "MCP server 未提供配置的工具: name=%s tool=%s 可用=%s",
            name,
            cfg.tool,
            sorted(tools),
        )
    handle = _ServerHandle(name=name, stack=stack, session=session, tools=tools)
    _handles[name] = handle
    logger.info("MCP server 已就绪: name=%s tools=%d", name, len(tools))
    return handle


async def _handle_for(name: str) -> _ServerHandle:
    """取会话；不存在则（加锁后二次检查）启动。"""
    handle = _handles.get(name)
    if handle is not None:
        return handle
    async with _get_start_lock():
        return _handles.get(name) or await _start(name)


def _normalize(server: str, result: Any) -> dict[str, Any]:
    """`CallToolResult` → 统一形状（结构化优先，文本兜底）。

    第三方 server 口径不一：有的只回文本、有的把返回值包成 `{"result": ...}`。
    这里只做**形状归一**，**语义校验与解包在领域适配器**（设计 §15.10）。
    """
    structured = getattr(result, "structuredContent", None)
    texts = [
        item.text
        for item in (getattr(result, "content", None) or [])
        if isinstance(getattr(item, "text", None), str)
    ]
    return {
        "server": server,
        "structured": structured if isinstance(structured, dict) else None,
        "text": "\n".join(texts),
        "is_error": bool(getattr(result, "isError", False)),
    }


async def call_configured(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """调用配置好的 server 的指定工具，返回归一化结果（见 `_normalize`）。"""
    if not settings.MCP_ENABLED:
        raise MCPError("MCP 未启用（MCP_ENABLED=false）")
    cfg = get_server(name)
    if cfg is None or not cfg.enabled:
        raise MCPError(f"未配置 MCP server：{name}")

    handle = await _handle_for(name)
    timeout = cfg.timeout_seconds or settings.MCP_CALL_TIMEOUT_SECONDS
    async with handle.lock:
        try:
            result = await asyncio.wait_for(
                handle.session.call_tool(cfg.tool, arguments), timeout=timeout
            )
        except TimeoutError as exc:
            # 超时会取消底层调用 → 会话不可复用，必须丢弃后重连
            await _drop(name, reason="超时")
            raise MCPError(f"MCP 调用超时（>{timeout}s）：{name}.{cfg.tool}") from exc
        except Exception as exc:
            await _drop(name, reason=f"异常:{type(exc).__name__}")
            logger.warning(
                "MCP 调用失败: name=%s tool=%s type=%s",
                name,
                cfg.tool,
                type(exc).__name__,
            )
            raise MCPError(f"MCP 调用失败：{name}.{cfg.tool}") from exc
    return _normalize(name, result)


async def close_mcp_clients() -> None:
    """关闭全部 server 子进程（应用 shutdown / 测试收尾）。"""
    for name in list(_handles):
        await _drop(name, reason="关闭")
    global _start_lock
    _start_lock = None
