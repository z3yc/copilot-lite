"""行情：外部数据校验 · 归一化 · 缓存（infra 领域适配层）。

职责边界（AGENTS §12 / 设计 §5.3/§15.10）：
- **MCP 返回一律不可信**：逐条校验（代码格式/净值范围/日期可解析/涨跌夹取），
  坏条丢弃 + WARNING，好条照常返回——**一条坏数据不能连坐整批**；
- **口径差异在本层吸收**：结构化优先、文本 JSON 兜底、`{"result": ...}` 包裹解包；
- **缓存**：命中窗口内（`FUND_QUOTE_CACHE_MINUTES`）直接复用，否则合并成**一次** MCP
  调用（F3 播报 N 支基金只打一次）；`(code, nav_date)` 幂等 upsert。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.json_parse import parse_json_object
from app.mcp.client import MCPError, call_configured
from app.mcp.registry import get_adapter, register_adapter
from app.models.fund_quote import FundQuoteCache

logger = logging.getLogger(__name__)

# 默认行情 server 名（与 deploy/.env.example 的 MCP_SERVERS 一致）
MCP_SERVER_DEFAULT = "fund-quotes"
# 适配器键（MCP_SERVERS[].adapter 引用它）
ADAPTER_FUND_NAV_V1 = "fund_nav_v1"

_CODE_RE = re.compile(r"^\d{6}$")
# 净值合理区间（外部数据范围夹取，AGENTS §6.6）
_NAV_MIN = Decimal(0)
_NAV_MAX = Decimal(1000000)
_PCT_MIN = Decimal(-100)
_PCT_MAX = Decimal(100)


@dataclass(frozen=True)
class FundQuote:
    """归一化后的单支基金行情（校验通过才会被构造出来）。"""

    code: str
    nav: Decimal
    nav_date: date
    prev_nav: Decimal | None
    change_pct: Decimal | None
    source: str
    fetched_at: datetime


def validate_code(code: str) -> bool:
    """基金代码：本项目只接受 6 位数字（场外基金代码口径）。"""
    return bool(_CODE_RE.fullmatch(code or ""))


def _utcnow() -> datetime:
    """当前 UTC（naive，与库中 DateTime 列一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _decimal(value: Any) -> Decimal | None:
    """宽松转 Decimal：拒绝 bool/空串/非有限值/非数字。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return parsed if parsed.is_finite() else None


def _parse_date(value: Any) -> date | None:
    """净值日期：支持 date 与 `YYYY-MM-DD`（含带时间的字符串）。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _clamp_pct(value: Any) -> Decimal | None:
    """涨跌幅夹取到 [-100, 100]；非数值 → None。"""
    parsed = _decimal(value)
    if parsed is None:
        return None
    return max(_PCT_MIN, min(_PCT_MAX, parsed))


def _parse_quote(raw: Any, *, source: str, now: datetime) -> FundQuote | None:
    """单条外部数据 → FundQuote；任一**硬**校验不过返回 None（调用方记日志）。"""
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("code") or "").strip()
    if not validate_code(code):
        return None
    nav = _decimal(raw.get("nav"))
    if nav is None or not (_NAV_MIN < nav < _NAV_MAX):
        return None
    nav_date = _parse_date(raw.get("nav_date"))
    if nav_date is None:
        return None
    prev = _decimal(raw.get("prev_nav"))
    prev_nav = prev if prev is not None and _NAV_MIN < prev < _NAV_MAX else None
    return FundQuote(
        code=code,
        nav=nav,
        nav_date=nav_date,
        prev_nav=prev_nav,
        change_pct=_clamp_pct(raw.get("change_pct")),
        source=source,
        fetched_at=now,
    )


def _unwrap(data: Any) -> Any:
    """剥掉第三方 server 的 `{"result": ...}` 包裹（FastMCP 对非 dict[str, …] 会包裹）。"""
    if isinstance(data, dict) and set(data) == {"result"} and isinstance(data["result"], dict):
        return data["result"]
    return data


def adapt_fund_nav_v1(payload: dict[str, Any], codes: list[str]) -> list[FundQuote]:
    """`adapter=fund_nav_v1`：MCP 归一化返回 → 校验后的 `FundQuote` 列表。

    `codes` 仅作上下文（哪些是被请求的代码），校验以返回内容为准；
    未返回的代码由上层如实标注「未取到」。
    """
    del codes  # 适配器不依赖请求列表（缺哪些由 payload["missing"] 说明）
    data = _unwrap(payload.get("structured"))
    if not isinstance(data, dict):
        data = parse_json_object(payload.get("text"))
    if not isinstance(data, dict) or not data:
        logger.warning("行情返回不可解析，整批丢弃: server=%s", payload.get("server"))
        return []

    source = f"mcp:{payload.get('server') or 'unknown'}"
    now = _utcnow()
    quotes: list[FundQuote] = []
    for raw in data.get("quotes") or []:
        quote = _parse_quote(raw, source=source, now=now)
        if quote is None:
            logger.warning(
                "行情脏数据已丢弃: server=%s code=%r nav=%r nav_date=%r",
                payload.get("server"),
                raw.get("code") if isinstance(raw, dict) else raw,
                raw.get("nav") if isinstance(raw, dict) else None,
                raw.get("nav_date") if isinstance(raw, dict) else None,
            )
            continue
        quotes.append(quote)
    return quotes


register_adapter(ADAPTER_FUND_NAV_V1, adapt_fund_nav_v1)


def _adapter_for(server: str) -> str:
    """该 server 配置的适配器键（缺配置时回退默认键）。"""
    from app.mcp.registry import get_server

    cfg = get_server(server)
    return cfg.adapter if cfg else ADAPTER_FUND_NAV_V1


async def _fetch_via_mcp(server: str, codes: list[str]) -> list[FundQuote]:
    """调 MCP 并走适配器；失败**不抛穿**（降级为「未取到」，AGENTS §10）。"""
    try:
        payload = await call_configured(server, {"codes": codes})
    except MCPError as exc:
        logger.warning("行情 MCP 调用失败，降级为未取到: server=%s err=%s", server, exc)
        return []
    adapter = get_adapter(_adapter_for(server))
    if adapter is None:  # pragma: no cover - 启动自检已拦截，此处仅防御
        logger.error("未注册的适配器: %s", _adapter_for(server))
        return []
    return adapter(payload, codes)


async def _load_cached(
    db: AsyncSession, codes: list[str], now: datetime
) -> dict[str, FundQuote]:
    """窗口内最新一条缓存（一次查询取回，避免 N+1）。"""
    since = now - timedelta(minutes=max(0, settings.FUND_QUOTE_CACHE_MINUTES))
    rows = (
        await db.scalars(
            select(FundQuoteCache)
            .where(FundQuoteCache.code.in_(codes), FundQuoteCache.fetched_at >= since)
            .order_by(FundQuoteCache.fetched_at.desc())
        )
    ).all()
    freshest: dict[str, FundQuote] = {}
    for row in rows:
        if row.code in freshest:
            continue
        freshest[row.code] = FundQuote(
            code=row.code,
            nav=row.nav,
            nav_date=row.nav_date,
            prev_nav=row.prev_nav,
            change_pct=row.change_pct,
            source=row.source,
            fetched_at=row.fetched_at,
        )
    return freshest


async def _upsert_quotes(
    db: AsyncSession, quotes: list[FundQuote], moment: datetime
) -> None:
    """按 `(code, nav_date)` 幂等写入（一条语句批量 upsert）。

    `fetched_at` 用**本次操作的时刻**（而非适配器里的当前时间）：
    同一次调用的「取数时间」与「缓存新鲜度判断」必须同一个刻度，否则注入时钟的
    调用方会得到自相矛盾的窗口（测试与将来定时任务都会踩）。
    """
    if not quotes:
        return
    rows = [
        {
            "code": q.code,
            "nav_date": q.nav_date,
            "nav": q.nav,
            "prev_nav": q.prev_nav,
            "change_pct": q.change_pct,
            "source": q.source,
            "fetched_at": moment,
        }
        for q in quotes
    ]
    stmt = pg_insert(FundQuoteCache).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fund_quotes_code_nav_date",
        set_={
            "nav": stmt.excluded.nav,
            "prev_nav": stmt.excluded.prev_nav,
            "change_pct": stmt.excluded.change_pct,
            "source": stmt.excluded.source,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def get_quotes(
    db: AsyncSession,
    codes: list[str],
    *,
    server: str = MCP_SERVER_DEFAULT,
    now: datetime | None = None,
) -> dict[str, FundQuote | None]:
    """批量取行情：缓存优先，未命中的代码合并成**一次** MCP 调用。

    返回 `{code: FundQuote | None}`；`None` = 如实「未取到」（不编造）。
    """
    moment = now or _utcnow()
    wanted: list[str] = []
    result: dict[str, FundQuote | None] = {}
    for raw in codes:
        code = (raw or "").strip()
        if not validate_code(code):
            logger.warning("非法基金代码，已忽略: %r", raw)
            result[code] = None
            continue
        if code not in wanted:
            wanted.append(code)
            result[code] = None

    if not wanted:
        return result

    result.update(await _load_cached(db, wanted, moment))
    missing = [code for code in wanted if result.get(code) is None]
    if not missing:
        return result

    fetched = await _fetch_via_mcp(server, missing)
    if fetched:
        await _upsert_quotes(db, fetched, moment)
    for quote in fetched:
        if quote.code in result:
            result[quote.code] = quote
    return result
