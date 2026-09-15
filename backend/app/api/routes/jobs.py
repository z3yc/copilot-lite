"""作业接口（OPTIMIZATION_PLAN 批次 J1）。

- GET  /jobs             本人作业列表（分页 + 状态/类型过滤）
- GET  /jobs/{id}        作业详情（状态/进度/结果/错误）
- POST /jobs/{id}/retry  重试失败/死信作业

归属隔离：一律按 `user_id` 过滤，他人作业返回 404（不泄露存在性，AGENTS §6.4）。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, parse_uuid
from app.core import jobs
from app.core.db import get_session
from app.core.pagination import DEFAULT_PAGE_SIZE, PageOut, normalize_page, page_offset
from app.models import Job, User

router = APIRouter(prefix="/jobs", tags=["jobs"])

# 可重试状态：失败（可重试中间态）与死信（重试耗尽）
_RETRYABLE = {"failed", "dead"}


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    progress: int
    attempts: int
    max_attempts: int
    error: str | None = None
    payload: dict = {}
    result: dict = {}
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


def _job_out(job: Job) -> JobOut:
    return JobOut(
        id=str(job.id),
        kind=job.kind,
        status=job.status,
        progress=job.progress,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error=job.error,
        payload=job.payload or {},
        result=job.result or {},
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def _get_own_job(db: AsyncSession, job_id: str, user: User) -> Job:
    """取本人作业；不存在或非本人一律 404（统一措辞，不泄露存在性）。"""
    job = await db.scalar(
        select(Job).where(Job.id == parse_uuid(job_id), Job.user_id == user.id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="作业不存在或无权访问")
    return job


@router.get("", response_model=PageOut[JobOut])
async def list_jobs(
    status: str | None = None,
    kind: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PageOut[JobOut]:
    """本人作业列表（分页，可按状态/类型过滤）。"""
    stmt = select(Job).where(Job.user_id == user.id)
    if status:
        stmt = stmt.where(Job.status == status)
    if kind:
        stmt = stmt.where(Job.kind == kind)
    stmt = stmt.order_by(Job.created_at.desc(), Job.id.desc())

    page, page_size = normalize_page(page, page_size)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset, limit = page_offset(page, page_size)
    rows = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    return PageOut(
        items=[_job_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobOut:
    """作业详情：状态/进度/结果/错误（供前端轮询）。"""
    return _job_out(await _get_own_job(db, job_id, user))


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobOut:
    """重试失败/死信作业：重置为 queued 并重新调度（开关关闭时仅排队）。"""
    job = await _get_own_job(db, job_id, user)
    if job.status not in _RETRYABLE:
        raise HTTPException(status_code=400, detail="该作业状态不可重试")
    await jobs.retry_job(db, job)
    await jobs.schedule_job(job.id)
    return _job_out(job)
