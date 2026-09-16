"""测试用 stdio MCP server：**生产 server 代码 + 假数据源**（零联网）。

用途有两层：
1. 让 client 的测试走**真 stdio 协议**（真子进程、真 initialize/tools/list/tools/call、
   真 JSON 序列化），同时满足 AGENTS §8「测试不得联网」；
2. `STUB_MODE=dirty` 可造脏数据（负净值/非数字/非法日期/超范围涨跌），
   供适配器的校验用例验证「坏条被逐条丢弃」。

模式：ok（默认）| dirty | missing | slow（睡 30s，测超时）| crash（启动即退出）。
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any


class StubProvider:
    """按 `STUB_MODE` 造数据的假数据源。"""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    async def fetch_nav(self, code: str) -> dict[str, Any] | None:
        if self.mode == "slow":
            await asyncio.sleep(30)
        if self.mode == "missing":
            return None
        if self.mode == "dirty":
            # 三种坏法各占一个代码：负净值 / 非法日期 / 超范围涨跌
            return {
                "code": code,
                "nav": "-1.23" if code == "000001" else "1.2500",
                "nav_date": "不是日期" if code == "000002" else "2026-09-15",
                "prev_nav": "1.2000",
                "change_pct": "999" if code == "000003" else "1.21",
            }
        return {
            "code": code,
            "nav": "1.2500",
            "nav_date": "2026-09-15",
            "prev_nav": "1.2350",
            "change_pct": "1.21",
        }


def main() -> None:
    mode = os.environ.get("STUB_MODE", "ok")
    if mode == "crash":
        sys.exit(3)  # 模拟 server 启动即崩

    from app.mcp_servers.fund_quotes.server import build_server

    build_server(StubProvider(mode)).run()


if __name__ == "__main__":
    main()
