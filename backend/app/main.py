"""应用入口：FastAPI 实例、生命周期、路由挂载。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models
from app.api import api_router
from app.core.config import settings
from app.core.constants import DEFAULT_USER_ID, DEFAULT_USERNAME
from app.core.db import Base, async_session_factory, engine
from app.core.logging import setup_logging
from app.models import User

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def _seed_default_user() -> None:
    """P1 简化：确保默认用户存在（单用户模式）。"""
    async with async_session_factory() as session:
        if await session.get(User, DEFAULT_USER_ID) is None:
            session.add(User(id=DEFAULT_USER_ID, username=DEFAULT_USERNAME, password_hash=""))
            await session.commit()
            logger.info("已创建默认用户: %s", DEFAULT_USERNAME)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期。

    本地开发模式自动建表（零依赖，便于快速上手）；
    生产/云端模式使用 Alembic 迁移管理表结构。
    """
    if settings.RUN_MODE == "local":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("本地模式：数据表已就绪")
    await _seed_default_user()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="个人 AI 智能助理后端服务",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict:
    return {
        "message": f"欢迎使用 {settings.APP_NAME}",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
