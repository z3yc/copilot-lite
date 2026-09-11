"""add wiki tables (spaces / pages / links)

Revision ID: e2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-11 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Wiki 空间 / 页面 / 链接图表。"""
    op.create_table(
        "wiki_spaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("root_path", sa.String(length=512), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wiki_spaces_owner_id", "wiki_spaces", ["owner_id"])

    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("space_id", sa.Uuid(), nullable=False),
        sa.Column("rel_path", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("mtime", sa.Float(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["space_id"], ["wiki_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("space_id", "rel_path", name="uq_wiki_page_space_path"),
    )
    op.create_index("ix_wiki_pages_user_id", "wiki_pages", ["user_id"])
    op.create_index("ix_wiki_pages_space_id", "wiki_pages", ["space_id"])
    op.create_index("ix_wiki_pages_slug", "wiki_pages", ["slug"])
    op.create_index("ix_wiki_pages_document_id", "wiki_pages", ["document_id"])

    op.create_table(
        "wiki_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("space_id", sa.Uuid(), nullable=False),
        sa.Column("source_page_id", sa.Uuid(), nullable=False),
        sa.Column("target_slug", sa.String(length=255), nullable=False),
        sa.Column("target_page_id", sa.Uuid(), nullable=True),
        sa.Column("alias", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["space_id"], ["wiki_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_page_id"], ["wiki_pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_page_id"], ["wiki_pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wiki_links_user_id", "wiki_links", ["user_id"])
    op.create_index("ix_wiki_links_space_id", "wiki_links", ["space_id"])
    op.create_index("ix_wiki_links_source_page_id", "wiki_links", ["source_page_id"])
    op.create_index("ix_wiki_links_target_slug", "wiki_links", ["target_slug"])
    op.create_index("ix_wiki_links_target_page_id", "wiki_links", ["target_page_id"])


def downgrade() -> None:
    """回滚：删除 Wiki 三表。"""
    op.drop_table("wiki_links")
    op.drop_table("wiki_pages")
    op.drop_table("wiki_spaces")
