"""add documents.content_hash

Revision ID: d5a1c7e9f2b3
Revises: b3d8e7f6a5c4
Create Date: 2026-09-11 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a1c7e9f2b3"
down_revision: str | Sequence[str] | None = "b3d8e7f6a5c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为 documents 增加 content_hash（内容去重键）+ 索引。"""
    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_documents_content_hash", "documents", ["content_hash"], unique=False
    )


def downgrade() -> None:
    """移除 content_hash 列与索引。"""
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
