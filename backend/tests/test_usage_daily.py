"""用量聚合测试（ADMIN_PLAN §9 N1.1）。

覆盖：usage_daily upsert 累加、按天分桶、成本计算、按 snapshot 增量采集、
采集失败静默（不影响主链路）。
"""

from datetime import UTC, datetime

import pytest

from app.core import usage as usage_module
from app.core.usage import compute_cost, record_from_snapshot, record_usage, snapshot_usage
from app.models import UsageDaily


@pytest.mark.asyncio
async def test_record_usage_accumulates(db_session) -> None:
    """同一用户同一天多次记录：requests/tokens/cost 累加（upsert 语义）。"""
    uid = "11111111-1111-1111-1111-111111111111"
    await record_usage(db_session, uid, tokens_in=100, tokens_out=50)
    row = await record_usage(db_session, uid, tokens_in=10, tokens_out=5, errors=1)

    rows = (await db_session.scalars(usage_select())).all()
    assert len(rows) == 1, "同用户同日应只有一行"
    assert rows[0].requests == 2
    assert rows[0].tokens_in == 110
    assert rows[0].tokens_out == 55
    assert rows[0].errors == 1
    assert row.day  # 有日期分桶


def usage_select():
    from sqlalchemy import select

    return select(UsageDaily)


@pytest.mark.asyncio
async def test_record_usage_separate_days(db_session) -> None:
    """不同日期分桶为两行。"""
    uid = "22222222-2222-2222-2222-222222222222"
    await record_usage(db_session, uid, tokens_in=1, day="2026-01-01")
    await record_usage(db_session, uid, tokens_in=2, day="2026-01-02")
    rows = (await db_session.scalars(usage_select())).all()
    assert {r.day for r in rows} == {"2026-01-01", "2026-01-02"}


def test_compute_cost(monkeypatch) -> None:
    """成本 = 输入/输出 token × 单价（每百万 token）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_PRICE_INPUT_PER_MTOK", 1.0)
    monkeypatch.setattr(settings, "LLM_PRICE_OUTPUT_PER_MTOK", 2.0)
    assert compute_cost(1_000_000, 1_000_000) == 3.0
    assert compute_cost(0, 0) == 0.0


@pytest.mark.asyncio
async def test_record_from_snapshot_deltas(db_session, monkeypatch) -> None:
    """按前后快照增量采集 tokens_in/tokens_out。"""
    before = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    after = {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45}
    monkeypatch.setattr(usage_module, "get_usage_stats", lambda: after)

    row = await record_from_snapshot(db_session, "33333333-3333-3333-3333-333333333333", before)
    assert row is not None
    assert row.tokens_in == 20
    assert row.tokens_out == 10


@pytest.mark.asyncio
async def test_record_from_snapshot_no_change_skips(db_session, monkeypatch) -> None:
    """无增量且无错误时跳过写入。"""
    stats = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    monkeypatch.setattr(usage_module, "get_usage_stats", lambda: stats)
    row = await record_from_snapshot(
        db_session, "44444444-4444-4444-4444-444444444444", snapshot_usage()
    )
    assert row is None


@pytest.mark.asyncio
async def test_record_usage_silently_swallows_error(db_session, monkeypatch) -> None:
    """采集异常被吞掉并返回 None（增强功能不能拖垮主链路）。"""

    async def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(usage_module, "record_from_snapshot", boom)
    result = await usage_module.record_usage_silently(db_session, "55555555-5555-5555-5555-555555555555")
    assert result is None


def test_today_format() -> None:
    """day 为 UTC 的 YYYY-MM-DD。"""
    assert usage_module._today() == datetime.now(UTC).strftime("%Y-%m-%d")
