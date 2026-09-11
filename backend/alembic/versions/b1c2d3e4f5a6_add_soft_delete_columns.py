"""add soft delete columns (deleted_at / deleted_by)

Revision ID: b1c2d3e4f5a6
Revises: e2b3c4d5e6f7
Create Date: 2026-09-11 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "e2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "documents",
    "chunks",
    "chat_sessions",
    "messages",
    "todos",
    "session_files",
    "memory_facts",
    "wiki_spaces",
    "wiki_pages",
)


def upgrade() -> None:
    """为业务表添加软删除字段（deleted_at + deleted_by）与索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for table in _TABLES:
        if table not in existing:
            continue
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(), nullable=True))
        op.add_column(table, sa.Column("deleted_by", sa.Uuid(), nullable=True))
        op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"], unique=False)


def downgrade() -> None:
    """移除软删除字段与索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for table in _TABLES:
        if table not in existing:
            continue
        op.drop_index(f"ix_{table}_deleted_at", table_name=table)
        op.drop_column(table, "deleted_by")
        op.drop_column(table, "deleted_at")
