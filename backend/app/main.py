"""应用入口：FastAPI 实例、生命周期、路由挂载。"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models
import app.tools  # 显式装配工具层：同时注册 MCP 领域适配器（启动自检依赖它）
from app.api import api_router
from app.core.config import settings
from app.core.context import RequestContextMiddleware
from app.core.db import Base, async_session_factory, engine
from app.core.envelope import EnvelopeMiddleware
from app.core.errors import AppError, code_for_status, envelope
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.mcp.client import close_mcp_clients
from app.mcp.registry import validate_configured_servers
from app.models import Category, User
from app.models.category import DEFAULT_CATEGORIES

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def _seed_super_admin() -> None:
    """种子超级管理员账号（仅当显式配置了非空密码）。

    超级管理员是唯一可用环境变量 Key 兜底的账号；不配密码则不创建，
    避免生成空密码/默认密码的高危账号（AGENTS §6）。
    """
    from sqlalchemy import select

    username = (settings.SUPER_ADMIN_USERNAME or "").strip()
    password = settings.SUPER_ADMIN_PASSWORD or ""
    if not username or not password:
        return
    async with async_session_factory() as session:
        user = await session.scalar(
            select(User).where(User.username == username, User.deleted_at.is_(None))
        )
        if user is None:
            session.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role="admin",
                )
            )
            await session.commit()
            logger.info("已创建超级管理员: %s", username)
        elif user.role != "admin":
            user.role = "admin"
            await session.commit()
            logger.info("已将账号提升为超级管理员: %s", username)


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


async def _prewarm_embeddings() -> None:
    """后台预热嵌入模型（首次会下载约 50MB；失败不影响服务启动）。

    背景：fastembed 默认缓存落 %TEMP%，被清理后每次加载都联网重下，首次同步会卡很久。
    预热 + 固定缓存目录（EMBEDDING_CACHE_DIR）可让后续使用改为纯本地。
    """
    from app.rag.embeddings import get_embedding_service

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, get_embedding_service().prewarm)
        logger.info("嵌入模型预热完成")
    except Exception:
        logger.warning("嵌入模型预热失败（首次使用时重试）", exc_info=True)
    if settings.RAG_RERANK_ENABLED:
        try:
            from app.rag.reranker import get_reranker

            await loop.run_in_executor(None, get_reranker().prewarm)
            logger.info("重排模型预热完成")
        except Exception:
            logger.warning("重排模型预热失败（首次使用时重试）", exc_info=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期。

    本地开发模式自动建表（零依赖，便于快速上手）；
    生产/云端模式使用 Alembic 迁移管理表结构。
    """
    # MCP 配置自检：引用了未注册的适配器 → 直接拒绝启动
    # （AGENTS §6/§7：坏配置要启动时就炸，不能等半夜播报才发现）
    validate_configured_servers()
    if settings.RUN_MODE == "local":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("本地模式：数据表已就绪")
    # 超级管理员仅当显式配置了密码时创建（唯一可用 env Key 兜底的账号）
    await _seed_super_admin()
    await _seed_categories()
    if settings.EMBEDDING_PREWARM:
        asyncio.create_task(_prewarm_embeddings())
    yield
    # 终止 MCP server 子进程（防进程泄漏）
    await close_mcp_clients()
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
