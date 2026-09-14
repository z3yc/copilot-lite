"""add usage_daily table

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-14 14:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建每日用量聚合表 usage_daily 与唯一/查询索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "usage_daily" in set(inspector.get_table_names()):
        return
    op.create_table(
        "usage_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day", name="uq_usage_daily_user_day"),
    )
    op.create_index("ix_usage_daily_user_id", "usage_daily", ["user_id"])
    op.create_index("ix_usage_daily_day", "usage_daily", ["day"])


def downgrade() -> None:
    """回滚：删除用量聚合表与索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "usage_daily" not in set(inspector.get_table_names()):
        return
    op.drop_index("ix_usage_daily_day", table_name="usage_daily")
    op.drop_index("ix_usage_daily_user_id", table_name="usage_daily")
    op.drop_table("usage_daily")
