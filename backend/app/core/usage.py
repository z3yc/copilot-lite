"""用量采集：把 LLM 进程级统计增量落到 `usage_daily`（ADMIN_PLAN §9 N1.1）。

设计：
- **按快照增量**：请求前后各取一次 `get_usage_stats()`，差值即本轮用量；
- **upsert 累加**：同用户同日一行，累加 requests / tokens_in / tokens_out / cost / errors；
- **成本按配置单价**：`LLM_PRICE_*_PER_MTOK`（默认 0 => 只统计 token 不计成本）；
- **失败静默**：``record_usage_silently`` 吞掉异常并记 warning，
  增强采集绝不拖垮对话主链路（AGENTS §10）。
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.llm import get_usage_stats
from app.models.usage_daily import UsageDaily

logger = logging.getLogger(__name__)


def _today() -> str:
    """UTC 日期字符串（YYYY-MM-DD）。"""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def compute_cost(tokens_in: int, tokens_out: int) -> float:
    """按每百万 token 单价计算成本（四舍五入到 6 位）。"""
    cost = (
        tokens_in / 1_000_000 * settings.LLM_PRICE_INPUT_PER_MTOK
        + tokens_out / 1_000_000 * settings.LLM_PRICE_OUTPUT_PER_MTOK
    )
    return round(cost, 6)


def snapshot_usage() -> dict:
    """当前进程级 LLM 用量快照（供请求前后求差）。"""
    return get_usage_stats()


async def record_usage(
    db: AsyncSession,
    user_id,
    *,
    tokens_in: int = 0,
    tokens_out: int = 0,
    requests: int = 1,
    errors: int = 0,
    day: str | None = None,
) -> UsageDaily:
    """累加某用户某天的用量（upsert：查不到则新建），提交后返回行。"""
    uid = uuid.UUID(str(user_id))
    key_day = day or _today()
    row = await db.scalar(
        select(UsageDaily).where(UsageDaily.user_id == uid, UsageDaily.day == key_day)
    )
    if row is None:
        row = UsageDaily(
            user_id=uid,
            day=key_day,
            requests=0,
            tokens_in=0,
            tokens_out=0,
            cost=0.0,
            errors=0,
        )
        db.add(row)
    row.requests += requests
    row.tokens_in += tokens_in
    row.tokens_out += tokens_out
    row.errors += errors
    row.cost = round(row.cost + compute_cost(tokens_in, tokens_out), 6)
    await db.commit()
    return row


async def record_from_snapshot(
    db: AsyncSession,
    user_id,
    before: dict,
    *,
    errors: int = 0,
) -> UsageDaily | None:
    """按前后快照的差值记入用量；无增量且无错误时跳过。"""
    after = get_usage_stats()
    delta_in = max(0, after.get("prompt_tokens", 0) - before.get("prompt_tokens", 0))
    delta_out = max(
        0, after.get("completion_tokens", 0) - before.get("completion_tokens", 0)
    )
    if delta_in == 0 and delta_out == 0 and errors == 0:
        return None
    return await record_usage(
        db, user_id, tokens_in=delta_in, tokens_out=delta_out, errors=errors
    )


async def record_usage_silently(
    db: AsyncSession,
    user_id,
    before: dict | None = None,
    *,
    errors: int = 0,
) -> UsageDaily | None:
    """采集失败不影响主链路（吞异常 + warning）。"""
    try:
        return await record_from_snapshot(
            db, user_id, before if before is not None else snapshot_usage(), errors=errors
        )
    except Exception:  # 采集是增强功能，绝不外抛
        logger.warning("usage_daily 记录失败（不影响主链路）", exc_info=True)
        return None
