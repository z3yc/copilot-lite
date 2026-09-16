"""add fund_quotes cache table (R4 / P-F1)

Revision ID: a4b5c6d7e8f9
Revises: e7f8a9b0c1d2
Create Date: 2026-09-16 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建公开行情缓存表 fund_quotes（无软删字段：临时表，见模型 docstring）。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "fund_quotes" in set(inspector.get_table_names()):
        return
    op.create_table(
        "fund_quotes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("nav_date", sa.Date(), nullable=False),
        sa.Column("nav", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("prev_nav", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("change_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", "nav_date", name="uq_fund_quotes_code_nav_date"),
    )
    op.create_index("ix_fund_quotes_code", "fund_quotes", ["code"])
    op.create_index("ix_fund_quotes_fetched_at", "fund_quotes", ["fetched_at"])


def downgrade() -> None:
    """回滚：删表（纯缓存，重建即可恢复，无业务数据丢失风险）。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "fund_quotes" not in set(inspector.get_table_names()):
        return
    op.drop_index("ix_fund_quotes_fetched_at", table_name="fund_quotes")
    op.drop_index("ix_fund_quotes_code", table_name="fund_quotes")
    op.drop_table("fund_quotes")
