"""评测作业机制：状态机 + 可开关后台 worker（ADMIN_PLAN §6 / AGENTS §8/§17）。

设计：
- **状态机**：`queued → running → done/failed`，进度/指标/错误落 `eval_runs`；
  失败留 error + finished_at，便于页面重试；
- **可开关**：`EVAL_JOB_ENABLED` 关闭时不创建后台任务（测试环境默认关，
  避免后台任务持有测试库句柄）；
- **并发上限**：进程内信号量（`EVAL_JOB_CONCURRENCY`），评测跑真实嵌入 /
  LLM judge，必须限并发防打爆；
- **超时**：`asyncio.wait_for(EVAL_JOB_TIMEOUT_SECONDS)` 防后台无限期挂起；
- **执行器可注入**：真实评测执行器在 N2.2 接入（`set_executor`），
  机制层与评测实现解耦、可 Fake 测试。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import async_session_factory
from app.models.eval_run import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    EvalRun,
)

logger = logging.getLogger(__name__)

Executor = Callable[[EvalRun, AsyncSession], Awaitable["EvalResult"]]

# 模块级可重置状态（AGENTS §8：全局状态必须可重置）
_executor: Executor | None = None
_semaphore: asyncio.Semaphore | None = None


@dataclass
class EvalResult:
    """一次评测执行的结果（指标 + 通过计数）。"""

    metrics: dict = field(default_factory=dict)
    total: int = 0
    passed: int = 0


def set_executor(executor: Executor | None) -> None:
    """注册真实评测执行器（N2.2 接入）。"""
    global _executor
    _executor = executor


def reset_eval_jobs() -> None:
    """重置模块级状态（测试隔离用）。"""
    global _executor, _semaphore
    _executor = None
    _semaphore = None


def _get_executor() -> Executor:
    if _executor is None:
        raise RuntimeError("评测执行器未注册（N2.2 接入 set_executor）")
    return _executor


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.EVAL_JOB_CONCURRENCY))
    return _semaphore


def _now() -> datetime:
    """当前 UTC 时间（naive，与库中 DateTime 列一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


async def process_run(
    db: AsyncSession,
    run_id,
    executor: Executor | None = None,
) -> EvalRun | None:
    """执行一次评测作业（状态机核心），返回更新后的 run。

    - run 不存在：安全返回 None（后台竞态/幂等）；
    - 已在 running：直接返回，防重复执行；
    - 成功：done + progress=100 + metrics/total/passed；
    - 超时/异常：failed + error + finished_at（可重试依据）。
    """
    run = await db.get(EvalRun, run_id)
    if run is None:
        logger.warning("评测作业不存在: run=%s", run_id)
        return None
    if run.status == STATUS_RUNNING:
        logger.info("评测作业已在运行，跳过: run=%s", run_id)
        return run

    fn = executor or _get_executor()
    run.status = STATUS_RUNNING
    run.started_at = _now()
    run.progress = 0
    run.error = None
    await db.commit()

    try:
        result = await asyncio.wait_for(
            fn(run, db), timeout=settings.EVAL_JOB_TIMEOUT_SECONDS
        )
    except TimeoutError:
        run.status = STATUS_FAILED
        run.error = "评测超时"
        logger.warning("评测作业超时: run=%s", run_id)
    except Exception as exc:
        run.status = STATUS_FAILED
        run.error = str(exc)[:1000]
        logger.exception("评测作业失败: run=%s", run_id)
    else:
        run.status = STATUS_DONE
        run.progress = 100
        run.metrics = result.metrics
        run.total = result.total
        run.passed = result.passed

    run.finished_at = _now()
    await db.commit()
    return run


async def schedule_eval_run(run_id) -> asyncio.Task | None:
    """把评测作业调度到后台（开关关闭时返回 None，不创建任务）。"""
    if not settings.EVAL_JOB_ENABLED:
        logger.info("评测作业开关关闭，跳过调度: run=%s", run_id)
        return None
    return asyncio.create_task(_run_guarded(run_id))


async def _run_guarded(run_id) -> None:
    """信号量限并发 + 独立 DB 会话的后台执行包装。"""
    sem = _get_semaphore()
    async with sem, async_session_factory() as db:
        try:
            await process_run(db, run_id)
        except Exception:
            logger.exception("评测后台任务未捕获异常: run=%s", run_id)
