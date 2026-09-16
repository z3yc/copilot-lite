"""**非基金域**的 stub MCP server：证明 `app/mcp` 与领域无关（接缝回归）。

主张「接入新 MCP 只加配置 + 适配器」（设计 §15.9/§15.10）必须有可执行证据：
这个 server 与基金毫无关系，client 不得为它改一行代码。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def build_generic_server() -> FastMCP:
    server: FastMCP = FastMCP("generic-echo")

    @server.tool(name="echo")
    async def echo(text: str) -> dict:
        """原样回显文本（测试用，无业务含义）。"""
        return {"echo": text}

    return server


def main() -> None:
    build_generic_server().run()


if __name__ == "__main__":
    main()
