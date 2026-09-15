"""通用后台作业机制（OPTIMIZATION_PLAN 批次 J1 / AGENTS §8/§17）。

定位：**慢摄取/同步不再阻塞 HTTP**——请求建作业并立即返回 `job_id`，
后台 worker 执行，前端轮询 `GET /jobs/{id}` 看进度与结果。

设计：
- **状态机**：`queued → running → done`；失败按 `max_attempts` 自动重试，
  耗尽置 `dead`（死信，可人工重试）；
- **可开关**：`JOBS_ENABLED` 关闭时不创建后台任务（测试环境默认关，
  避免后台任务持有测试库句柄，AGENTS §8）；
- **限并发 + 超时**：进程内信号量（`JOBS_CONCURRENCY`）+ `wait_for`
  （`JOBS_TIMEOUT_SECONDS`），防慢任务打爆进程 / 无限期挂起；
- **handler 注册表**：core 不感知具体业务；业务方 `register_handler(kind, fn)`，
  机制层与摄取实现解耦、可用 Fake 测试。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import async_session_factory
from app.models.job import (
    STATUS_DEAD,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    Job,
)

logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, Job], Awaitable[dict]]

# 模块级可重置状态（AGENTS §8：全局状态必须可重置）
_handlers: dict[str, Handler] = {}
_semaphore: asyncio.Semaphore | None = None


def register_handler(kind: str, handler: Handler | None) -> None:
    """注册/注销某类作业的处理器（业务方调用，如 wiki_sync）。"""
    if handler is None:
        _handlers.pop(kind, None)
    else:
        _handlers[kind] = handler


def get_handler(kind: str) -> Handler | None:
    """取某类作业的处理器（未注册返回 None）。"""
    return _handlers.get(kind)


def reset_jobs() -> None:
    """重置运行时状态（测试隔离用）。

    注意：**不清空 handler 注册表**——注册表由各业务模块在 import 时建立，
    清空会让“重置”变成“卸载业务”（其他模块的异步作业变成未注册→死信，
    且表现为与测试执行顺序相关的隐慢 bug）。
    """
    global _semaphore
    _semaphore = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.JOBS_CONCURRENCY))
    return _semaphore


def _now() -> datetime:
    """当前 UTC 时间（naive，与库中 DateTime 列一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


async def submit_job(
    db: AsyncSession,
    *,
    user_id,
    kind: str,
    payload: dict | None = None,
    max_attempts: int | None = None,
) -> Job:
    """建一个 queued 作业（真正执行交给 run_job / schedule_job）。"""
    job = Job(
        kind=kind,
        user_id=user_id,
        payload=payload or {},
        max_attempts=max_attempts or settings.JOBS_MAX_ATTEMPTS,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info("作业已提交: kind=%s job=%s user=%s", kind, job.id, user_id)
    return job


async def run_job(
    db: AsyncSession,
    job_id,
    *,
    handler: Handler | None = None,
) -> Job | None:
    """执行作业（状态机核心），返回更新后的 job。

    - job 不存在：安全返回 None（后台竞态/重复调度幂等）；
    - 已完成/执行中：直接返回，防重复摄取；
    - 成功：done + progress=100 + result；
    - 失败：按 max_attempts 自动重试，耗尽置 dead + error + finished_at。
    """
    job = await db.get(Job, job_id)
    if job is None:
        logger.warning("作业不存在: job=%s", job_id)
        return None
    if job.status in (STATUS_DONE, STATUS_RUNNING):
        logger.info("作业无需执行: job=%s status=%s", job_id, job.status)
        return job

    if handler is None:
        handler = get_handler(job.kind)
    if handler is None:
        # 未注册：重试也不会变，直接死信（错误可读，不抛穿后台任务）
        job.attempts += 1
        job.status = STATUS_DEAD
        job.error = f"未注册的作业类型: {job.kind}"
        job.finished_at = _now()
        await db.commit()
        logger.error("未注册的作业类型: kind=%s job=%s", job.kind, job.id)
        return job

    max_attempts = max(1, job.max_attempts)
    while job.attempts < max_attempts:
        job.attempts += 1
        job.status = STATUS_RUNNING
        job.started_at = _now()
        job.progress = 0
        job.error = None
        await db.commit()

        try:
            result = await asyncio.wait_for(
                handler(db, job), timeout=settings.JOBS_TIMEOUT_SECONDS
            )
        except TimeoutError:
            job.status = STATUS_FAILED
            job.error = f"作业超时（>{settings.JOBS_TIMEOUT_SECONDS}s）"
            logger.warning("作业超时: kind=%s job=%s", job.kind, job.id)
        except Exception as exc:
            job.status = STATUS_FAILED
            job.error = str(exc)[:1000]
            logger.exception("作业执行失败: kind=%s job=%s", job.kind, job.id)
        else:
            job.status = STATUS_DONE
            job.result = result or {}
            job.progress = 100
            job.finished_at = _now()
            await db.commit()
            logger.info("作业完成: kind=%s job=%s", job.kind, job.id)
            return job

        if job.attempts >= max_attempts:
            job.status = STATUS_DEAD
        await db.commit()

    job.finished_at = _now()
    await db.commit()
    logger.error(
        "作业进入死信: kind=%s job=%s attempts=%s", job.kind, job.id, job.attempts
    )
    return job


async def retry_job(db: AsyncSession, job: Job) -> Job:
    """人工重试：重置为 queued 并清零尝试次数（供失败/死信作业重跑）。"""
    job.status = STATUS_QUEUED
    job.attempts = 0
    job.progress = 0
    job.error = None
    job.finished_at = None
    await db.commit()
    await db.refresh(job)
    logger.info("作业已重置待重试: job=%s", job.id)
    return job


async def schedule_job(job_id) -> asyncio.Task | None:
    """把作业调度到后台（开关关闭时返回 None，不创建任务）。"""
    if not settings.JOBS_ENABLED:
        logger.info("作业开关关闭，跳过调度: job=%s", job_id)
        return None
    return asyncio.create_task(_run_guarded(job_id))


async def _run_guarded(job_id) -> None:
    """信号量限并发 + 独立 DB 会话的后台执行包装。"""
    sem = _get_semaphore()
    async with sem, async_session_factory() as db:
        try:
            await run_job(db, job_id)
        except Exception:
            logger.exception("后台作业未捕获异常: job=%s", job_id)
