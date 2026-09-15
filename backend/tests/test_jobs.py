"""通用作业机制测试（OPTIMIZATION_PLAN 批次 J1）。

覆盖：
- 提交建 queued 作业（owner/kind/payload 落库）；
- 状态机：queued → running → done（进度 100 + result）；
- 失败自动重试至 max_attempts → 死信（dead）+ error；
- 超时按失败处理（防后台无限期挂起，AGENTS §17）；
- 未注册 kind → 死信（错误可读，不炸后台）；
- 幂等：done/running 的作业不重复执行；
- 后台调度开关（测试默认关，AGENTS §8）；
- 模块级状态可重置（AGENTS §8）。
"""

import asyncio
import uuid

import pytest

from app.core import jobs
from app.core.config import settings
from app.core.db import async_session_factory
from app.models import Job


async def _make_job(db, **kw) -> Job:
    """建一个作业（测试用，默认 kind=demo、单次尝试）。"""
    kw.setdefault("kind", "demo")
    kw.setdefault("user_id", uuid.uuid4())
    kw.setdefault("max_attempts", 1)
    job = Job(**kw)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@pytest.mark.asyncio
async def test_submit_job_creates_queued_job(db_session) -> None:
    """提交作业：落库为 queued，携带 owner/kind/payload。"""
    uid = uuid.uuid4()
    job = await jobs.submit_job(
        db_session, user_id=uid, kind="demo", payload={"a": 1}
    )
    assert job.id is not None
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.payload == {"a": 1}
    assert job.user_id == uid
    assert job.max_attempts == settings.JOBS_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_run_job_success_sets_done_and_result(db_session) -> None:
    """执行成功：done + 进度 100 + result 落库 + 起止时间。"""
    job = await _make_job(db_session)

    async def handler(_db, _job) -> dict:
        return {"added": 3}

    got = await jobs.run_job(db_session, job.id, handler=handler)

    assert got is not None
    assert got.status == "done"
    assert got.progress == 100
    assert got.result == {"added": 3}
    assert got.attempts == 1
    assert got.started_at is not None
    assert got.finished_at is not None
    assert got.error is None


@pytest.mark.asyncio
async def test_run_job_retries_then_dead(db_session) -> None:
    """失败按 max_attempts 自动重试，耗尽后置死信 dead 并记录 error。"""
    job = await _make_job(db_session, max_attempts=3)
    calls: list[int] = []

    async def handler(_db, _job) -> dict:
        calls.append(1)
        raise RuntimeError("boom")

    got = await jobs.run_job(db_session, job.id, handler=handler)

    assert got is not None
    assert got.status == "dead"
    assert got.attempts == 3
    assert len(calls) == 3
    assert "boom" in (got.error or "")
    assert got.finished_at is not None


@pytest.mark.asyncio
async def test_run_job_timeout_marked_dead(db_session, monkeypatch) -> None:
    """作业超时：wait_for 中断，按失败处理（超时不计入无限挂起）。"""
    monkeypatch.setattr(settings, "JOBS_TIMEOUT_SECONDS", 0.01)
    job = await _make_job(db_session)

    async def handler(_db, _job) -> dict:
        await asyncio.sleep(0.2)
        return {}

    got = await jobs.run_job(db_session, job.id, handler=handler)

    assert got is not None
    assert got.status == "dead"
    assert "超时" in (got.error or "")


@pytest.mark.asyncio
async def test_run_job_missing_returns_none(db_session) -> None:
    """作业不存在：安全返回 None（后台竞态/重复调度幂等）。"""
    assert await jobs.run_job(db_session, uuid.uuid4(), handler=None) is None


@pytest.mark.asyncio
async def test_run_job_unregistered_kind_dead(db_session) -> None:
    """未注册的 kind：置死信并给出可读错误，而不是抛穿后台任务。"""
    job = await _make_job(db_session, kind="nope-never-registered")

    got = await jobs.run_job(db_session, job.id)

    assert got is not None
    assert got.status == "dead"
    assert "未注册" in (got.error or "")


@pytest.mark.asyncio
async def test_run_job_done_is_idempotent(db_session) -> None:
    """已完成的作业不再重复执行（防重复调度重复摄取）。"""
    job = await _make_job(db_session, status="done")
    calls: list[int] = []

    async def handler(_db, _job) -> dict:
        calls.append(1)
        return {}

    got = await jobs.run_job(db_session, job.id, handler=handler)

    assert got is not None
    assert got.status == "done"
    assert calls == []


@pytest.mark.asyncio
async def test_schedule_disabled_returns_none(monkeypatch) -> None:
    """JOBS_ENABLED=false 时不创建后台任务（测试默认关，AGENTS §8）。"""
    monkeypatch.setattr(settings, "JOBS_ENABLED", False)
    assert await jobs.schedule_job(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_schedule_enabled_runs_job(monkeypatch, db_session) -> None:
    """开关打开时后台任务被调度并执行到 done（独立 DB 会话）。"""
    monkeypatch.setattr(settings, "JOBS_ENABLED", True)
    jobs.reset_jobs()
    calls: list[str] = []

    async def handler(_db, _job) -> dict:
        calls.append(str(_job.id))
        return {"ok": True}

    jobs.register_handler("demo", handler)

    async with async_session_factory() as db:
        job = Job(kind="demo", user_id=uuid.uuid4(), max_attempts=1)
        db.add(job)
        await db.commit()
        jid = job.id

    task = await jobs.schedule_job(jid)
    assert task is not None
    await task
    assert calls == [str(jid)]

    async with async_session_factory() as db:
        got = await db.get(Job, jid)
        assert got is not None
        assert got.status == "done"

    jobs.register_handler("demo", None)


@pytest.mark.asyncio
async def test_reset_jobs_keeps_handlers() -> None:
    """reset_jobs 只重置运行时状态，不清空业务 handler 注册表。

    回归：曾把注册表一并清空，导致 wiki_sync 等模块级注册丢失——
    后续用例的异步作业全部变成“未注册→死信”（与测试执行顺序相关的隐性 bug）。
    """

    async def handler(_db, _job) -> dict:
        return {}

    jobs.register_handler("demo_reset", handler)
    try:
        jobs.reset_jobs()
        assert jobs.get_handler("demo_reset") is handler
    finally:
        jobs.register_handler("demo_reset", None)
