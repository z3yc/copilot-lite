"""users: soft delete + status + partial unique username index

Revision ID: b4c5d6e7f8a9
Revises: a3f1c2d4e5b6
Create Date: 2026-09-14 13:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3f1c2d4e5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_COLUMNS = ("deleted_at", "deleted_by", "delete_reason", "status")


def _index_names(inspector, table: str) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade() -> None:
    """users 增加软删除字段 + status；username 唯一约束改部分唯一索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}

    if "deleted_at" not in columns:
        op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    if "deleted_by" not in columns:
        op.add_column("users", sa.Column("deleted_by", sa.Uuid(), nullable=True))
    if "delete_reason" not in columns:
        op.add_column("users", sa.Column("delete_reason", sa.String(length=255), nullable=True))
    if "status" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'active'"),
            ),
        )

    indexes = _index_names(inspector, "users")
    if "ix_users_deleted_at" not in indexes:
        op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    # 旧的全表唯一索引 → 非唯一索引（唯一性交由部分唯一索引保证）
    if "ix_users_username" in indexes:
        op.drop_index("ix_users_username", table_name="users")
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    if "uq_users_username_active" not in indexes:
        op.create_index(
            "uq_users_username_active",
            "users",
            ["username"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    """回滚：移除部分唯一索引与软删除/状态字段，恢复全表唯一索引。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}
    indexes = _index_names(inspector, "users")

    if "uq_users_username_active" in indexes:
        op.drop_index("uq_users_username_active", table_name="users")
    if "ix_users_username" in indexes:
        op.drop_index("ix_users_username", table_name="users")
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    if "ix_users_deleted_at" in indexes:
        op.drop_index("ix_users_deleted_at", table_name="users")

    for column in ("status", "delete_reason", "deleted_by", "deleted_at"):
        if column in columns:
            op.drop_column("users", column)
