"""add session_files.bytes_size

Revision ID: b3d8e7f6a5c4
Revises: c9f4e8a2b7d1
Create Date: 2026-08-27 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d8e7f6a5c4'
down_revision: str | Sequence[str] | None = 'c9f4e8a2b7d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为 session_files 增加 bytes_size（真实文件字节数，size 字段语义修正）。"""
    op.add_column(
        'session_files',
        sa.Column('bytes_size', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """移除 bytes_size 列。"""
    op.drop_column('session_files', 'bytes_size')
