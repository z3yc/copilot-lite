"""基金净值工具：对话路径的领域入口（设计 §6 / §15.4）。

- **LLM 只见本工具**，不见 MCP 原始 schema：换 server/换数据源只改适配器（P0.5）；
- 契约 **F1 起即最终形态** `fund_query(ctx, codes=None)`：F2 接上持仓后
  「codes 为空 = 查全部持仓」自然生效，**工具名/参数/描述零变更**；
- 只读，不进 HITL（写操作在 F2 的持仓工具，届时 `requires_confirmation=True`）；
- 一切失败都转成可读文本（不抛穿 Agent 循环，AGENTS §4/§10）。
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.core.prompts.fund import (
    FUND_DATA_NOTICE,
    FUND_NO_POSITION_NOTICE,
    FUND_NO_SOURCE_NOTICE,
)
from app.funds.quotes import MCP_SERVER_DEFAULT, FundQuote, get_quotes, validate_code
from app.mcp.registry import get_server
from app.tools.base import ToolContext, registry

logger = logging.getLogger(__name__)

MAX_CODES = 20  # 对话场景一次问不了那么多支


@registry.register
async def fund_query(ctx: ToolContext, codes: list[str] | None = None) -> str:
    """查询基金最新单位净值（数据来自第三方公开接口，可能延迟，请以净值日期为准）；codes 为空时查询本人持仓。"""
    if not settings.MCP_ENABLED or get_server(MCP_SERVER_DEFAULT) is None:
        return FUND_NO_SOURCE_NOTICE

    raw_codes = [str(code).strip() for code in (codes or []) if str(code).strip()]
    if not raw_codes:
        return FUND_NO_POSITION_NOTICE

    unique = list(dict.fromkeys(raw_codes))[:MAX_CODES]
    valid = [code for code in unique if validate_code(code)]
    invalid = [code for code in unique if not validate_code(code)]
    if not valid:
        return f"基金代码格式不正确（需 6 位数字）：{', '.join(invalid)}"

    try:
        quotes: dict[str, FundQuote | None] = await get_quotes(ctx.session, valid)
    except Exception:
        logger.exception("基金行情查询失败: codes=%s", valid)
        return "基金行情查询失败，请稍后再试。"

    lines = [FUND_DATA_NOTICE]
    for code in valid:
        quote = quotes.get(code)
        if quote is None:
            lines.append(f"- {code}：未取到最新净值")
            continue
        text = f"- {quote.code}：单位净值 {quote.nav}（净值日期 {quote.nav_date.isoformat()}）"
        if quote.change_pct is not None:
            text += f"，当日涨跌 {quote.change_pct}%"
        lines.append(text)
    if invalid:
        lines.append(f"- 以下代码格式不正确已忽略：{', '.join(invalid)}")
    return "\n".join(lines)
