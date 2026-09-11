"""应用入口：FastAPI 实例、生命周期、路由挂载。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models
from app.api import api_router
from app.core.config import settings
from app.core.constants import DEFAULT_USER_ID, DEFAULT_USERNAME
from app.core.context import RequestContextMiddleware
from app.core.db import Base, async_session_factory, engine
from app.core.envelope import EnvelopeMiddleware
from app.core.errors import AppError, code_for_status, envelope
from app.core.logging import setup_logging
from app.models import Category, User
from app.models.category import DEFAULT_CATEGORIES

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def _seed_default_user() -> None:
    """P1 简化：确保默认用户存在（单用户模式）。"""
    async with async_session_factory() as session:
        if await session.get(User, DEFAULT_USER_ID) is None:
            session.add(User(id=DEFAULT_USER_ID, username=DEFAULT_USERNAME, password_hash=""))
            await session.commit()
            logger.info("已创建默认用户: %s", DEFAULT_USERNAME)


async def _seed_categories() -> None:
    """为没有分类的用户补齐默认 4 类（工作/生活/学习/其他）。"""
    from sqlalchemy import select


    async with async_session_factory() as session:
        users = (await session.scalars(select(User.id))).all()
        for uid in users:
            exists = await session.scalar(
                select(Category.id).where(Category.user_id == uid).limit(1)
            )
            if exists is None:
                for c in DEFAULT_CATEGORIES:
                    session.add(Category(user_id=uid, **c))
                logger.info("已为用户 %s 补齐默认分类", uid)
        await session.commit()


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
    # 默认用户仅为本地单用户模式的历史简化；云模式不 seed 空密码账号
    if settings.RUN_MODE == "local":
        await _seed_default_user()
    await _seed_categories()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="个人 AI 智能助理后端服务",
    lifespan=lifespan,
)

# CORS：本地开发前端（Vite 5173）与云端部署域名按配置放行
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求级上下文（request_id 全链路追踪 + 响应头回写）
app.add_middleware(RequestContextMiddleware)

# 统一响应结构：/api/v1 成功 JSON 包成 {code, message, data}
app.add_middleware(EnvelopeMiddleware)

app.include_router(api_router, prefix="/api/v1")


# ---------------- 统一错误响应（AGENTS.md §14） ----------------


@app.exception_handler(AppError)
async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(code=exc.code, message=exc.message),
    )


@app.exception_handler(StarletteHTTPException)
async def _handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(code=code_for_status(exc.status_code), message=detail),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=envelope(code=1000, message="参数校验失败"),
    )


@app.exception_handler(Exception)
async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content=envelope(code=3000, message="服务内部错误"),
    )


@app.get("/")
async def root() -> dict:
    return {
        "message": f"欢迎使用 {settings.APP_NAME}",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
