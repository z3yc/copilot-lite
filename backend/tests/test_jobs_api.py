"""作业 API 测试（OPTIMIZATION_PLAN 批次 J1）。

覆盖：详情/列表/重试接口的**归属隔离**（他人作业 404，不泄露存在性，
AGENTS §6.4）、分页契约（§14）、重试的状态约束。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import async_session_factory
from app.main import app
from app.models import Job


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _job_for(uid: str, **kw) -> str:
    """直接落一个作业（跳过接口，便于构造各种状态）。"""
    async with async_session_factory() as db:
        job = Job(kind=kw.pop("kind", "demo"), user_id=uuid.UUID(uid), **kw)
        db.add(job)
        await db.commit()
        return str(job.id)


@pytest.mark.asyncio
async def test_get_job_detail(client, authed_headers) -> None:
    """详情：返回本人作业的状态/进度/尝试次数。"""
    jid = await _job_for(authed_headers["uid"])

    r = await client.get(f"/api/v1/jobs/{jid}", headers=authed_headers)

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == jid
    assert data["kind"] == "demo"
    assert data["status"] == "queued"
    assert data["progress"] == 0
    assert data["attempts"] == 0


@pytest.mark.asyncio
async def test_job_detail_other_user_404(client, authed_headers) -> None:
    """他人作业：404（统一"不存在或无权限"，不泄露资源存在性）。"""
    other = await _job_for(str(uuid.uuid4()))

    r = await client.get(f"/api/v1/jobs/{other}", headers=authed_headers)

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_only_mine(client, authed_headers) -> None:
    """列表：仅返回本人作业，且符合分页契约。"""
    mine = await _job_for(authed_headers["uid"], kind="mine")
    await _job_for(str(uuid.uuid4()), kind="theirs")

    r = await client.get("/api/v1/jobs", headers=authed_headers)

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["page"] == 1
    assert [item["id"] for item in data["items"]] == [mine]


@pytest.mark.asyncio
async def test_list_jobs_filter_by_status(client, authed_headers) -> None:
    """列表支持按状态过滤（排障：只看死信）。"""
    await _job_for(authed_headers["uid"], status="done", progress=100)
    dead = await _job_for(authed_headers["uid"], status="dead", attempts=2)

    r = await client.get("/api/v1/jobs?status=dead", headers=authed_headers)

    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert [item["id"] for item in items] == [dead]


@pytest.mark.asyncio
async def test_retry_dead_job(client, authed_headers) -> None:
    """重试死信作业：重置为 queued 并清零尝试次数与错误。"""
    jid = await _job_for(
        authed_headers["uid"], status="dead", attempts=2, error="boom"
    )

    r = await client.post(f"/api/v1/jobs/{jid}/retry", headers=authed_headers)

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "queued"
    assert data["attempts"] == 0
    assert data["error"] is None


@pytest.mark.asyncio
async def test_retry_done_job_rejected(client, authed_headers) -> None:
    """已完成作业不可重试（400）：避免重复摄取。"""
    jid = await _job_for(authed_headers["uid"], status="done", progress=100)

    r = await client.post(f"/api/v1/jobs/{jid}/retry", headers=authed_headers)

    assert r.status_code == 400


@pytest.mark.asyncio
async def test_retry_other_user_job_404(client, authed_headers) -> None:
    """重试他人作业：404（与详情同样的隔离语义）。"""
    other = await _job_for(str(uuid.uuid4()), status="dead")

    r = await client.post(f"/api/v1/jobs/{other}/retry", headers=authed_headers)

    assert r.status_code == 404
