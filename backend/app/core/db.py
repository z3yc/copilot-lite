"""数据库层：异步 engine / session 工厂 / ORM 基类。

开发模式默认 SQLite（aiosqlite），生产通过 DATABASE_URL 切换 PostgreSQL（asyncpg）。
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""


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
