"""健康检查路由：存活（liveness）与就绪（readiness）分离。

- GET /health          旧版兼容（仅返回自身信息，恒 200）
- GET /health/live     存活探针：进程可响应即 200（K8s/容器不因依赖抖动重启）
- GET /health/ready    就绪探针：探 DB 与向量库，任一不可用返回 503（负载均衡摘除）

分离的意义（面试可讲）：liveness 失败 = 重启进程；readiness 失败 = 暂不接流量。
把依赖故障放进 liveness 会导致"依赖一抖动就无限重启"，是常见反模式。
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.db import async_session_factory
from app.rag import vector_store as vector_store_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "run_mode": settings.RUN_MODE,
    }


@router.get("/health/live")
async def live() -> dict:
    """存活探针：进程能响应即视为存活。"""
    return {"status": "ok"}


async def _check_database() -> bool:
    """数据库连通性（SELECT 1）。"""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001  探针失败按不可用处理
        logger.warning("就绪检查：数据库不可用: %s", exc)
        return False


def _check_vector_store() -> bool:
    """向量库连通性（列出集合）。"""
    try:
        vector_store_module.get_qdrant_client().get_collections()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("就绪检查：向量库不可用: %s", exc)
        return False


@router.get("/health/ready")
async def ready() -> JSONResponse:
    """就绪探针：依赖全部可用返回 200，否则 503（附各项明细）。"""
    checks = {
        "database": await _check_database(),
        "vector_store": _check_vector_store(),
    }
    ok = all(checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "checks": checks},
    )
