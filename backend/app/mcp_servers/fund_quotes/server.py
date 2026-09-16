"""基金净值 MCP server（stdio）：把公开行情包成标准 MCP 工具。

设计（设计 §15.1/§15.5）：
- 自建最小 server：真 stdio + `tools/list` + `tools/call`；client 只认 `.env` 配置，
  换第三方 server 时本文件根本不参与；
- `build_server(provider)` 可注入数据源 → 测试用 Fake provider **复用本文件**
  （真协议 + 假数据，零联网），生产用 `EastmoneyProvider`；
- 只暴露**一个结构化工具**，且不把上游字段名原样透传给 LLM：换 server 只改适配器，
  工具 schema 与 prompt 不动（P0.5）。
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp_servers.fund_quotes.eastmoney import EastmoneyProvider, QuoteProvider

SERVER_NAME = "fund-quotes"
TOOL_NAME = "get_fund_nav"
# 单次调用最多查询的代码数（防超量请求打爆上游）
MAX_CODES = 50


def build_server(provider: QuoteProvider | None = None) -> FastMCP:
    """构建 server（provider 可注入；缺省走东方财富公开接口）。"""
    source = provider if provider is not None else EastmoneyProvider()
    server: FastMCP = FastMCP(SERVER_NAME)

    @server.tool(name=TOOL_NAME)
    async def get_fund_nav(codes: list[str]) -> dict[str, Any]:
        """批量查询基金最新单位净值（公开数据，可能延迟，请以净值日期为准）。"""
        found: list[dict[str, Any]] = []
        missing: list[str] = []
        # 去重保序 + 截断（上游参数同样不可信）
        for code in list(dict.fromkeys(codes))[:MAX_CODES]:
            raw = await source.fetch_nav(code)
            if raw is None:
                missing.append(code)
            else:
                found.append(raw)
        return {"quotes": found, "missing": missing}

    return server


def main() -> None:
    """stdio 入口（`python -m app.mcp_servers.fund_quotes`）。"""
    build_server().run()
