"""通用 MCP stdio 客户端（infra 层，**不感知任何领域**）。

契约：`call_configured(server_name, arguments)`——server 名与工具名都来自 `.env`
的 `MCP_SERVERS`（管理员级白名单）。本模块对「基金」一无所知；接入新 MCP 只需
「加配置 + 写适配器」（见 `app/mcp/__init__.py` 的四步清单）。

## 生命周期：为什么会话由「专用拥有者任务」持有

`mcp` 的 `stdio_client` 内部是 anyio task group + cancel scope，它们**必须由创建
它们的任务来退出**。若把会话存在请求任务里、又在别的任务（或 `asyncio.wait_for`
新建的任务）里关闭，anyio 会抛
`RuntimeError: Attempted to exit cancel scope in a different task`，
**关闭动作失败而子进程泄漏**（真机实测踩到，且被 `except` 吞掉变得无声）。

因此：每个 server 一个常驻的**拥有者任务** `_serve()`，
`initialize`/`tools/call`/关闭全部发生在该任务内；请求方只做两件事——
把调用放进队列、必要时 `cancel()` 这个任务（取消会传播进任务组，由 anyio 正常收尾）。

其余设计（设计 §5.2/§15.10）：
- **懒启动**：首次调用才拉起子进程；`tools/list` 结果缓存供将来披露/白名单使用；
- **常驻复用**：子进程不随请求启停；
- **失败即丢弃会话（含超时）**：下次调用自动重连；
- **降级不炸**：`MCP_ENABLED=false` / 未配置 / 单 server `enabled=false` → 抛 `MCPError`，
  由领域工具转成可读提示（AGENTS §10 失败回退优先可用性）。

安全：日志只打 server 名/工具名/异常类型；`env` 值永不打印（AGENTS §6.1/§6.8）。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

from app.core.config import settings
from app.mcp.registry import get_server, truncate_description

logger = logging.getLogger(__name__)


class MCPError(RuntimeError):
    """MCP 调用失败（未配置/超时/协议错误），上层转可读提示。"""


@dataclass
class _Call:
    """一次待执行的调用（请求方 → 拥有者任务）。"""

    tool: str
    arguments: dict[str, Any]
    future: asyncio.Future


@dataclass
class _ServerOwner:
    """server 会话的持有者（其 `task` 即拥有者任务）。"""

    name: str
    queue: asyncio.Queue[_Call | None] = field(default_factory=asyncio.Queue)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    tools: dict[str, str] = field(default_factory=dict)
    error: Exception | None = None


# 模块级可变状态（AGENTS §8：必须可重置——用 `close_mcp_clients()`）
_owners: dict[str, _ServerOwner] = {}
_start_lock: asyncio.Lock | None = None


def _get_start_lock() -> asyncio.Lock:
    global _start_lock
    if _start_lock is None:
        _start_lock = asyncio.Lock()
    return _start_lock


def _backend_dir() -> str:
    """backend 根目录：作为子进程默认 cwd（保证 `python -m app.xxx` 可导入）。"""
    return str(Path(__file__).resolve().parents[2])


def _build_params(cfg) -> StdioServerParameters:
    """构造子进程启动参数（`command` 留空 = 当前解释器）。"""
    return StdioServerParameters(
        # 避开 Windows `python` 商店桩
        command=cfg.command or sys.executable,
        args=list(cfg.args),
        # env 显式给出时才覆盖：与 SDK 的安全默认环境合并，带上自定义 Key
        env={**get_default_environment(), **cfg.env} if cfg.env else None,
        cwd=cfg.cwd or _backend_dir(),
    )


def _fail_pending(owner: _ServerOwner) -> None:
    """把队列里未处理的请求全部置错（避免调用方永久挂住）。"""
    while not owner.queue.empty():
        call = owner.queue.get_nowait()
        if call is None or call.future.done():
            continue
        call.future.set_exception(owner.error or MCPError(f"MCP 会话已关闭：{owner.name}"))


async def _serve(name: str) -> None:
    """拥有者任务：会话的进入、调用与退出**全部在本任务内完成**（见模块 docstring）。"""
    owner = _owners[name]
    cfg = get_server(name)
    if cfg is None:
        owner.error = MCPError(f"未配置 MCP server：{name}")
        owner.ready.set()
        return
    try:
        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(stdio_client(_build_params(cfg)))
            session: ClientSession = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            owner.tools = {
                tool.name: truncate_description(getattr(tool, "description", None))
                for tool in listed.tools
            }
            if cfg.tool not in owner.tools:
                logger.warning(
                    "MCP server 未提供配置的工具: name=%s tool=%s 可用=%s",
                    name,
                    cfg.tool,
                    sorted(owner.tools),
                )
            owner.ready.set()
            logger.info("MCP server 已就绪: name=%s tools=%d", name, len(owner.tools))

            while True:
                call = await owner.queue.get()
                if call is None:  # 优雅停止信号
                    break
                try:
                    result = await session.call_tool(call.tool, call.arguments)
                except Exception as exc:  # noqa: BLE001  工具层任何异常都要回传给调用方，
                    # 不能让它变成未处理异常炸掉拥有者任务（否则后续请求全部悬死）
                    if not call.future.done():
                        call.future.set_exception(exc)
                    continue
                if not call.future.done():
                    call.future.set_result(result)
    except asyncio.CancelledError:
        # 取消是「丢弃会话」的正常路径：会话已由上面的 async with 关闭
        logger.info("MCP 会话被取消（丢弃）: name=%s", name)
        raise
    except Exception as exc:  # noqa: BLE001  会话层任何失败都必须转成 error 通知等待者，
        # 裸抛会变成「任务悄悄死掉、请求永久挂住」（AGENTS §10 失败回退优先可用性）
        logger.warning("MCP server 会话异常: name=%s type=%s", name, type(exc).__name__)
        owner.error = MCPError(f"MCP server 启动失败：{name}")
    finally:
        _fail_pending(owner)
        owner.ready.set()  # 兜底：任何路径都不能让等待者永久挂住


async def _owner_for(name: str) -> _ServerOwner:
    """取（或懒启动）server 的拥有者任务，并等它就绪。"""

    def _alive(candidate: _ServerOwner | None) -> bool:
        return candidate is not None and candidate.task is not None and not candidate.task.done()

    async def _ready_or_raise(candidate: _ServerOwner) -> _ServerOwner:
        await candidate.ready.wait()
        if candidate.error is not None:
            raise candidate.error
        return candidate

    current = _owners.get(name)
    if _alive(current):
        return await _ready_or_raise(current)

    async with _get_start_lock():
        current = _owners.get(name)
        if _alive(current):
            return await _ready_or_raise(current)
        owner = _ServerOwner(name=name)
        _owners[name] = owner
        owner.task = asyncio.create_task(_serve(name), name=f"mcp-server:{name}")
        return await _ready_or_raise(owner)


async def _drop(name: str, *, reason: str) -> None:
    """丢弃会话：取消拥有者任务（**由该任务自己退出 anyio 取消域**）。"""
    owner = _owners.pop(name, None)
    if owner is None:
        return
    logger.info("已丢弃 MCP 会话: name=%s reason=%s", name, reason)
    task = owner.task
    if task is None or task.done():
        return
    task.cancel()
    # gather 把 CancelledError 当结果收下：不吞调用方自身的取消语义
    await asyncio.gather(task, return_exceptions=True)


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

    owner = await _owner_for(name)
    timeout = cfg.timeout_seconds or settings.MCP_CALL_TIMEOUT_SECONDS
    call = _Call(
        tool=cfg.tool,
        arguments=dict(arguments),
        future=asyncio.get_running_loop().create_future(),
    )
    owner.queue.put_nowait(call)
    try:
        result = await asyncio.wait_for(call.future, timeout=timeout)
    except TimeoutError as exc:
        # 超时后会话状态可疑 → 丢弃（下次自动重连）；注意这里取消的是**拥有者任务**，
        # 而不是正在进行的 stdio 调用本身（取消后者会搅坏流，同 R3 流式教训）
        await _drop(name, reason="超时")
        raise MCPError(f"MCP 调用超时（>{timeout}s）：{name}.{cfg.tool}") from exc
    except MCPError:
        raise
    except Exception as exc:
        await _drop(name, reason=f"异常:{type(exc).__name__}")
        logger.warning(
            "MCP 调用失败: name=%s tool=%s type=%s", name, cfg.tool, type(exc).__name__
        )
        raise MCPError(f"MCP 调用失败：{name}.{cfg.tool}") from exc
    return _normalize(name, result)


async def close_mcp_clients() -> None:
    """关闭全部 server 子进程（应用 shutdown / 测试收尾）。"""
    for name in list(_owners):
        await _drop(name, reason="关闭")
    global _start_lock
    _start_lock = None
