"""数据库层：异步 engine / session 工厂 / ORM 基类。

统一 PostgreSQL（asyncpg）：本地开发、测试、生产同一方言，
避免"测试用 SQLite 通过、生产 PG 报错"的方言差异。
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import DateTime, Uuid
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""


class SoftDeleteMixin:
    """软删除：业务数据删除只标记，不物理删除（AGENTS §13）。

    - `deleted_at`：删除时间；查询层默认过滤 `IS NULL`。
    - `deleted_by`：操作者用户 id（可空，兼容系统/历史数据）。
    派生索引（向量/分块）可在软删除时清理，恢复时重建。
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：为每个请求提供一个独立的数据库会话。"""
    async with async_session_factory() as session:
        yield session
