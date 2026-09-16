"""行情缓存表：唯一约束、精度、以及「刻意不做软删除」的防回归。"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.db import async_session_factory
from app.models.fund_quote import FundQuoteCache
from tests.support.timeutil import naive_utc


def _row(**kw) -> FundQuoteCache:
    base = {
        "code": "000001",
        "nav_date": date(2026, 9, 15),
        "nav": Decimal("1.2500"),
        "prev_nav": Decimal("1.2350"),
        "change_pct": Decimal("1.2100"),
        "source": "mcp:fund-quotes",
        "fetched_at": naive_utc(2026, 9, 15, 21, 30),
    }
    base.update(kw)
    return FundQuoteCache(**base)


async def test_unique_code_and_nav_date() -> None:
    async with async_session_factory() as db:
        db.add(_row())
        await db.commit()
        db.add(_row(nav=Decimal("1.3000")))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_numeric_precision_is_four_decimals() -> None:
    async with async_session_factory() as db:
        db.add(_row(nav=Decimal("1.2345"), prev_nav=None, change_pct=Decimal("-0.0001")))
        await db.commit()
    async with async_session_factory() as db:
        row = await db.get(FundQuoteCache, 1)
        assert row.nav == Decimal("1.2345")
        assert row.prev_nav is None
        assert row.change_pct == Decimal("-0.0001")


def test_cache_table_has_no_soft_delete_columns() -> None:
    """公开行情缓存 = 临时表（设计 §15.3）：**故意**无 deleted_at/deleted_by。

    本用例是防回归：若有人「顺手」给它加软删字段，这里会立刻失败，
    迫使其先回答「缓存是否属于业务/用户数据」（AGENTS §6.11）。
    """
    cols = set(FundQuoteCache.__table__.columns.keys())
    assert "deleted_at" not in cols
    assert "deleted_by" not in cols
    assert "user_id" not in cols  # 公开数据，多用户共享同一份


def test_model_registered_in_metadata() -> None:
    import app.models  # noqa: F401  触发模型注册
    from app.core.db import Base

    assert "fund_quotes" in Base.metadata.tables
