"""公开行情缓存表（批次 P / R4）。

定位与边界（面试可讲）：这张表是**公开行情缓存**，不是业务数据——
- 无 `user_id`：同一天同一支基金的净值对所有人是同一份，多用户共享（设计 §5.4）；
- **不做软删除**：按 AGENTS §6.11「物理删除仅限…日志/临时表」按临时表处理，
  与业务表（必须软删）刻意区分；`(code, nav_date)` 唯一约束使它天然幂等 upsert；
- 金额/净值一律 `Numeric(18,4)` + `Decimal`：财务数据禁用 float
  （浮点误差会滚成「少算 0.01 元」，设计 §3.1）。

`prev_nav` 存上一净值日的单位净值，供 F3 算「当日盈亏」
（东财 `f10/lsjz` 一次返回相邻两期即可得，见 `app/mcp_servers/fund_quotes/eastmoney.py`）。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FundQuoteCache(Base):
    """单支基金某一净值日的行情（公开数据缓存，多用户共享）。"""

    __tablename__ = "fund_quotes"
    __table_args__ = (
        UniqueConstraint("code", "nav_date", name="uq_fund_quotes_code_nav_date"),
    )

    # 缓存表用自增整型主键：无跨系统引用需求，也不需要全局唯一标识
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    nav_date: Mapped[date] = mapped_column(Date)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    prev_nav: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    # 来源标识（哪个 server/adapter 给的）：换第三方 server 后可对账
    source: Mapped[str] = mapped_column(String(64))
    # 取数时间：缓存新鲜度只由它决定（净值日期可能因节假日不前进）
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
