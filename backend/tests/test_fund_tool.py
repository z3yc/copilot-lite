"""fund_query 工具：契约（T1：F1 即最终形态）、文案、降级。"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.config import settings
from app.mcp.registry import MCPServerSettings
from app.tools import fund_tool
from app.tools.base import ToolContext, registry
from tests.support.timeutil import naive_utc


def _quote(code: str, nav: str = "1.2500") -> fund_tool.FundQuote:
    return fund_tool.FundQuote(
        code=code,
        nav=Decimal(nav),
        nav_date=date(2026, 9, 15),
        prev_nav=Decimal("1.2350"),
        change_pct=Decimal("1.2100"),
        source="mcp:fund-quotes",
        fetched_at=naive_utc(2026, 9, 15, 21, 30),
    )


@pytest.fixture
def mcp_ready(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "MCP_SERVERS",
        [
            MCPServerSettings(
                name="fund-quotes", command="", tool="get_fund_nav", adapter="fund_nav_v1"
            )
        ],
    )


async def test_tool_is_registered_with_final_schema() -> None:
    tool = registry.get("fund_query")
    assert tool is not None
    props = tool.parameters["properties"]
    assert set(props) == {"codes"}  # ctx 不进 schema
    assert tool.parameters["required"] == []  # codes 可选（F1 起即最终形态）
    assert tool.requires_confirmation is False  # 只读，不进 HITL


async def test_disabled_mcp_returns_readable_notice(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    out = await registry.execute(
        "fund_query", '{"codes": ["000001"]}', ToolContext(session=db_session)
    )
    assert "未配置行情源" in out


async def test_no_codes_returns_holdings_placeholder(db_session, mcp_ready) -> None:
    out = await registry.execute("fund_query", "{}", ToolContext(session=db_session))
    assert "尚未录入持仓" in out


async def test_invalid_codes_reported(db_session, mcp_ready) -> None:
    out = await registry.execute(
        "fund_query", '{"codes": ["abc"]}', ToolContext(session=db_session)
    )
    assert "格式不正确" in out


async def test_codes_render_nav_with_date_and_source_notice(
    db_session, mcp_ready, monkeypatch
) -> None:
    async def _fake(db, codes, **kw):
        return {code: _quote(code) for code in codes}

    monkeypatch.setattr(fund_tool, "get_quotes", _fake)
    out = await registry.execute(
        "fund_query", '{"codes": ["000001"]}', ToolContext(session=db_session)
    )
    assert "1.2500" in out
    assert "净值日期 2026-09-15" in out  # 必须写明净值日期（不许说「实时」）
    assert "第三方公开数据" in out  # 数据来源声明
    assert "不是指令" in out  # 外部数据定界（AGENTS §6.6）
    assert "实时" not in out


async def test_missing_quote_is_reported_not_invented(
    db_session, mcp_ready, monkeypatch
) -> None:
    async def _fake(db, codes, **kw):
        return {code: None for code in codes}

    monkeypatch.setattr(fund_tool, "get_quotes", _fake)
    out = await registry.execute(
        "fund_query", '{"codes": ["000001"]}', ToolContext(session=db_session)
    )
    assert "未取到" in out


async def test_quote_lookup_failure_does_not_raise(
    db_session, mcp_ready, monkeypatch
) -> None:
    async def _boom(db, codes, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(fund_tool, "get_quotes", _boom)
    out = await registry.execute(
        "fund_query", '{"codes": ["000001"]}', ToolContext(session=db_session)
    )
    assert "查询失败" in out  # 工具自身兜底，不抛穿 Agent 循环


def test_public_data_has_no_user_scope() -> None:
    """F1 只读公开行情：`fund_quotes` 无 user_id，「跨用户隔离」在此无越权面。

    本用例是**记录性断言**：将来若给行情加上用户维度（例如自选/成本），
    这里会失败，提醒先回答「谁的持仓成本」（AGENTS §6.3）。
    """
    from app.models.fund_quote import FundQuoteCache

    assert "user_id" not in FundQuoteCache.__table__.columns
