"""add memory_facts table

Revision ID: 2898b892e706
Revises: 1473b855e26a
Create Date: 2026-08-25 15:10:39.539105

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2898b892e706'
down_revision: str | Sequence[str] | None = '1473b855e26a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建 memory_facts 表（模型 MemoryFact；此前 autogenerate 后为空，
    # 云端迁移链不会建表，长期记忆功能将报 relation does not exist）
    op.create_table(
        "memory_facts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "source_session_id",
            sa.Uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_memory_facts_user_id"), "memory_facts", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_memory_facts_user_id"), table_name="memory_facts")
    op.drop_table("memory_facts")
