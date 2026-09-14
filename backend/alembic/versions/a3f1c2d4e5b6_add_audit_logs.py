"""add audit_logs table

Revision ID: a3f1c2d4e5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-09-14 12:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f1c2d4e5b6"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建追加型审计表 audit_logs 与查询索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "audit_logs" in set(inspector.get_table_names()):
        return
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    """回滚：删除审计表与索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "audit_logs" not in set(inspector.get_table_names()):
        return
    for index in (
        "ix_audit_logs_created_at",
        "ix_audit_logs_action",
        "ix_audit_logs_user_id",
        "ix_audit_logs_request_id",
    ):
        op.drop_index(index, table_name="audit_logs")
    op.drop_table("audit_logs")
