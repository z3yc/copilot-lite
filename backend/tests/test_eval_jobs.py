"""评测作业机制测试（ADMIN_PLAN §6 / §9 N0.5）。

覆盖状态机：queued→running→done/failed、进度、超时、执行器未注册；
以及后台调度开关（EVAL_JOB_ENABLED）。
"""

import asyncio
import uuid

import pytest

from app.core import eval_jobs
from app.core.config import settings
from app.core.db import async_session_factory
from app.models import EvalRun


async def _make_run(db, **kw) -> EvalRun:
    run = EvalRun(status="queued", trigger="manual", **kw)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_process_run_success(db_session) -> None:
    """执行成功：running→done，进度 100、指标/计数落库。"""
    run = await _make_run(db_session)

    async def executor(_run, _db) -> eval_jobs.EvalResult:
        return eval_jobs.EvalResult(metrics={"recall": 0.9}, total=10, passed=9)

    result = await eval_jobs.process_run(db_session, run.id, executor=executor)

    assert result is not None
    assert result.status == "done"
    assert result.progress == 100
    assert result.metrics == {"recall": 0.9}
    assert result.total == 10
    assert result.passed == 9
    assert result.started_at is not None
    assert result.finished_at is not None
    assert result.error is None


@pytest.mark.asyncio
async def test_process_run_failure_records_error(db_session) -> None:
    """执行异常：状态 failed，error 落库，结束时间写入（可重试依据）。"""
    run = await _make_run(db_session)

    async def executor(_run, _db) -> eval_jobs.EvalResult:
        raise RuntimeError("judge 挂了")

    result = await eval_jobs.process_run(db_session, run.id, executor=executor)

    assert result is not None
    assert result.status == "failed"
    assert "judge" in (result.error or "")
    assert result.finished_at is not None


@pytest.mark.asyncio
async def test_process_run_timeout(db_session, monkeypatch) -> None:
    """执行超时：被 wait_for 中断，状态 failed、error 标注超时。"""
    monkeypatch.setattr(settings, "EVAL_JOB_TIMEOUT_SECONDS", 0.01)
    run = await _make_run(db_session)

    async def slow(_run, _db) -> eval_jobs.EvalResult:
        await asyncio.sleep(0.2)
        return eval_jobs.EvalResult(metrics={}, total=0, passed=0)

    result = await eval_jobs.process_run(db_session, run.id, executor=slow)

    assert result is not None
    assert result.status == "failed"
    assert "超时" in (result.error or "")


@pytest.mark.asyncio
async def test_process_run_missing_returns_none(db_session) -> None:
    """run 不存在时安全返回 None（后台任务幂等/竞态防炸）。"""
    result = await eval_jobs.process_run(
        db_session,
        uuid.uuid4(),
        executor=lambda *_: None,  # 不会被调用
    )
    assert result is None


@pytest.mark.asyncio
async def test_schedule_disabled_returns_none(monkeypatch) -> None:
    """EVAL_JOB_ENABLED=false 时不创建后台任务（测试默认关，AGENTS §8）。"""
    monkeypatch.setattr(settings, "EVAL_JOB_ENABLED", False)
    assert await eval_jobs.schedule_eval_run(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_schedule_enabled_runs_job(monkeypatch, db_session) -> None:
    """开关打开时后台任务被调度并执行到 done（独立 DB 会话）。"""
    monkeypatch.setattr(settings, "EVAL_JOB_ENABLED", True)
    eval_jobs.reset_eval_jobs()
    calls: list[str] = []

    async def executor(_run, _db) -> eval_jobs.EvalResult:
        calls.append(str(_run.id))
        return eval_jobs.EvalResult(metrics={"mrr": 1.0}, total=1, passed=1)

    eval_jobs.set_executor(executor)

    async with async_session_factory() as db:
        run = EvalRun(status="queued", trigger="manual")
        db.add(run)
        await db.commit()
        rid = run.id

    task = await eval_jobs.schedule_eval_run(rid)
    assert task is not None
    await task
    assert calls == [str(rid)]

    async with async_session_factory() as db:
        got = await db.get(EvalRun, rid)
        assert got is not None
        assert got.status == "done"

    eval_jobs.reset_eval_jobs()
