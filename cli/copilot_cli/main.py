"""Copilot-Lite CLI：个人 AI 助理命令行入口。

通过 HTTP 调用后端 API（Agent 的工具调用在后端完成）。
用法：
    copilot chat          # 交互式对话
    copilot ask "问题"     # 单次提问
"""

import os
import sys

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown

# Windows 控制台默认 GBK，无法编码 emoji/扩展字符（如 ✅ \u2705）；
# 强制标准输出为 UTF-8，避免 rich 渲染时 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(help="Copilot-Lite 个人 AI 助理")
console = Console()

API_BASE = os.environ.get("COPILOT_API_URL", "http://127.0.0.1:8000")


def _ask(message: str, session_id: str | None) -> tuple[str, str]:
    """调用后端聊天接口，返回 (回复, 会话id)。"""
    payload: dict = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    try:
        resp = httpx.post(f"{API_BASE}/api/v1/chat", json=payload, timeout=120)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response else str(exc)
        raise typer.Exit(f"后端返回错误 {exc.response.status_code}: {detail}") from exc
    except httpx.RequestError as exc:
        raise typer.Exit(f"无法连接后端（{API_BASE}），请先启动服务: uv run uvicorn app.main:app --reload") from exc

    data = resp.json()
    return data["reply"], data["session_id"]


@app.command()
def ask(message: str) -> None:
    """单次提问，例如: copilot ask "帮我列出待办事项" """
    reply, _ = _ask(message, None)
    console.print(Markdown(reply))


@app.command()
def chat() -> None:
    """交互式对话（输入 exit / quit 退出，会话自动延续）。"""
    console.print("[bold green]🤖 Copilot-Lite[/] 就绪，输入消息开始对话（[dim]exit[/dim] 退出）")
    session_id: str | None = None
    while True:
        try:
            message = typer.prompt("你")
        except (EOFError, KeyboardInterrupt):
            break
        if message.strip().lower() in {"exit", "quit", "q"}:
            break
        if not message.strip():
            continue
        reply, session_id = _ask(message, session_id)
        console.print(Markdown(reply))
        console.print()


if __name__ == "__main__":
    app()
