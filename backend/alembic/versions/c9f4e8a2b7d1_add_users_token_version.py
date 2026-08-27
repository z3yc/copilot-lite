"""add users.token_version

Revision ID: c9f4e8a2b7d1
Revises: 2898b892e706
Create Date: 2026-08-27 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9f4e8a2b7d1'
down_revision: str | Sequence[str] | None = '2898b892e706'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为 users 表增加 token_version 列（JWT 无状态撤销：改密后旧 token 失效）。"""
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """移除 token_version 列。"""
    op.drop_column('users', 'token_version')
