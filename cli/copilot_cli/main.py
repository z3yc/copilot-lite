"""Copilot-Lite CLI：个人 AI 助理命令行入口。

通过 HTTP 调用后端 API（Agent 的工具调用在后端完成）。
用法：
    copilot login               # 登录（保存令牌）
    copilot whoami              # 查看当前登录状态
    copilot chat                # 交互式对话
    copilot ask "问题"           # 单次提问
    copilot todo list           # 直接管理待办
    copilot todo add "标题"      # 创建待办
    copilot todo done <id>      # 完成待办
    copilot todo rm <id>        # 删除待办
"""

import os
import sys

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from copilot_cli.auth import (
    auth_header,
    clear_credentials,
    get_token,
    get_username,
    save_credentials,
)

# Windows 控制台默认 GBK，无法编码 emoji/扩展字符（如 ✅ \u2705）；
# 强制标准输出为 UTF-8，避免 rich 渲染时 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(help="Copilot-Lite 个人 AI 助理")
console = Console()

API_BASE = os.environ.get("COPILOT_API_URL", "http://127.0.0.1:8000")


def _request(method: str, path: str, **kwargs):
    """后端请求封装：统一错误处理 + 自动注入登录令牌。"""
    headers = {**auth_header(), **(kwargs.pop("headers", None) or {})}
    try:
        resp = httpx.request(
            method, f"{API_BASE}{path}", timeout=120, headers=headers, **kwargs
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401 and not path.startswith("/api/v1/auth"):
            # 认证失败给出可执行指引，而非裸 401
            raise typer.Exit(
                "未登录或登录已过期，请先运行: copilot login"
            ) from exc
        detail = exc.response.text[:300] if exc.response else str(exc)
        raise typer.Exit(f"后端返回错误 {status}: {detail}") from exc
    except httpx.RequestError as exc:
        raise typer.Exit(
            f"无法连接后端（{API_BASE}），请先启动服务: uv run uvicorn app.main:app --reload"
        ) from exc


def _ask(message: str, session_id: str | None) -> tuple[str, str]:
    """调用后端聊天接口，返回 (回复, 会话id)。"""
    payload: dict = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    data = _request("POST", "/api/v1/chat", json=payload)
    return data["reply"], data["session_id"]


@app.command()
def login(
    username: str | None = typer.Option(None, "--username", "-u", help="用户名（缺省交互输入）"),
    register: bool = typer.Option(False, "--register", help="用户名不存在时顺便注册新账号"),
) -> None:
    """登录并保存令牌；--register 可同时注册新账号。"""
    if get_token() and not register:
        console.print(
            f"[yellow]当前已登录（{get_username() or '未知用户'}）[/yellow]，"
            "如需切换请先 copilot logout"
        )
        return
    username = username or typer.prompt("用户名")
    password = typer.prompt("密码", hide_input=True)
    path = "/api/v1/auth/register" if register else "/api/v1/auth/login"
    data = _request("POST", path, json={"username": username, "password": password})
    save_credentials(data["token"], username)
    console.print(f"[green]✅ 已登录[/green] {username}（令牌已保存到本地）")


@app.command()
def logout() -> None:
    """退出登录（删除本地令牌）。"""
    if clear_credentials():
        console.print("[green]已退出登录[/green]")
    else:
        console.print("[dim]当前未登录[/dim]")


@app.command()
def whoami() -> None:
    """查看当前登录状态与账号信息。"""
    if get_token() is None:
        console.print("[yellow]未登录[/yellow]，运行 `copilot login` 登录")
        return
    data = _request("GET", "/api/v1/auth/me")
    console.print(
        f"[green]已登录[/green] {data['username']}（id: {str(data['id'])[:8]}）"
    )


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


# ---------------- 待办直接管理 ----------------

todo_app = typer.Typer(help="直接管理待办事项（不走 Agent）")
app.add_typer(todo_app, name="todo")


@todo_app.command("list")
def todo_list(status: str | None = typer.Option(None, "--status", help="过滤: pending/done")):
    """列出待办事项。"""
    path = "/api/v1/todos" + (f"?status={status}" if status else "")
    todos = _request("GET", path)
    if not todos:
        console.print("[dim]暂无待办事项[/dim]")
        return
    table = Table(title="待办事项", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("标题")
    table.add_column("状态")
    table.add_column("优先级")
    for t in todos:
        status_text = "✅ 已完成" if t["status"] == "done" else "⬜ 待办"
        table.add_row(t["id"][:8], t["title"], status_text, str(t["priority"]))
    console.print(table)


@todo_app.command("add")
def todo_add(
    title: str,
    priority: int = typer.Option(3, "--priority", min=1, max=5, help="优先级 1-5"),
    due: str | None = typer.Option(None, "--due", help="截止日期 YYYY-MM-DD"),
):
    """创建待办，例如: copilot todo add "学习 React" --priority 1 --due 2026-01-01"""
    data = _request("POST", "/api/v1/todos", json={"title": title, "priority": priority, "due_date": due})
    console.print(f"[green]已创建[/green] {data['title']}（id: {data['id'][:8]}）")


@todo_app.command("done")
def todo_done(todo_id: str):
    """按 id 完成待办。"""
    data = _request("PATCH", f"/api/v1/todos/{todo_id}", json={"status": "done"})
    console.print(f"[green]已完成[/green] {data['title']}")


@todo_app.command("rm")
def todo_rm(todo_id: str):
    """按 id 删除待办。"""
    _request("DELETE", f"/api/v1/todos/{todo_id}")
    console.print(f"[yellow]已删除[/yellow] {todo_id[:8]}")


if __name__ == "__main__":
    app()
