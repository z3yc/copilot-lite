"""add llm_settings table

Revision ID: f1a2b3c4d5e6
Revises: d5a1c7e9f2b3
Create Date: 2026-09-11 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d5a1c7e9f2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """用户模型配置表（每用户一条；API Key 加密存储）。"""
    op.create_table(
        "llm_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_settings_user_id", "llm_settings", ["user_id"], unique=True)


def downgrade() -> None:
    """回滚：删除 llm_settings 表。"""
    op.drop_index("ix_llm_settings_user_id", table_name="llm_settings")
    op.drop_table("llm_settings")
