"""管理后台概览与用量时间序列测试（ADMIN_PLAN §9 N1.2/N1.4）。"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import DEFAULT_USER_ID
from app.core.db import async_session_factory
from app.main import app
from app.models import EvalRun, UsageDaily, User


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


async def _seed(db) -> None:
    db.add(
        UsageDaily(
            user_id=DEFAULT_USER_ID,
            day=_today(),
            requests=3,
            tokens_in=300,
            tokens_out=150,
            cost=0.01,
            errors=1,
        )
    )
    db.add(
        UsageDaily(
            user_id=DEFAULT_USER_ID,
            day="2020-01-01",
            requests=1,
            tokens_in=10,
            tokens_out=5,
            cost=0.0,
            errors=0,
        )
    )
    db.add(
        EvalRun(
            status="done",
            trigger="manual",
            source_scope="all",
            metrics={"recall@5": 0.8},
            total=10,
            passed=8,
            progress=100,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_overview_kpis(client, admin_headers) -> None:
    """概览 KPI：用户数、今日用量、错误率、最新评测分。"""
    async with async_session_factory() as db:
        await _seed(db)

    r = await client.get("/api/v1/admin/overview", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["users_total"] >= 1
    assert data["admins"] >= 1
    assert data["requests_today"] >= 3
    assert data["tokens_in_today"] >= 300
    assert data["tokens_out_today"] >= 150
    assert data["latest_eval"] is not None
    assert data["latest_eval"]["metrics"]["recall@5"] == 0.8


@pytest.mark.asyncio
async def test_usage_series_aggregates(client, admin_headers) -> None:
    """用量时间序列：按天聚合，支持用户过滤。"""
    async with async_session_factory() as db:
        await _seed(db)

    r = await client.get("/api/v1/admin/usage?days=7", headers=admin_headers)
    assert r.status_code == 200
    points = {p["day"]: p for p in r.json()["data"]}
    assert _today() in points
    assert points[_today()]["requests"] >= 3

    r = await client.get(
        f"/api/v1/admin/usage?days=7&user_id={DEFAULT_USER_ID}", headers=admin_headers
    )
    assert r.status_code == 200
    assert any(p["tokens_in"] >= 300 for p in r.json()["data"])

    # 畸形 user_id 安全返回空列表
    r = await client.get("/api/v1/admin/usage?user_id=not-a-uuid", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["data"] == []


@pytest.mark.asyncio
async def test_overview_and_usage_direct(db_session, admin_headers) -> None:
    """直接调用 handler：覆盖聚合/边界分支。"""
    from app.api.routes import admin as admin_module

    async with async_session_factory() as db:
        await _seed(db)
        admin_user = await db.get(User, uuid.UUID(admin_headers["uid"]))

        overview = await admin_module.overview(db=db, admin=admin_user)
        assert overview.users_total >= 1
        assert overview.latest_eval is not None

        series = await admin_module.usage_series(
            days=7, user_id=None, db=db, admin=admin_user
        )
        assert len(series) >= 1

        empty = await admin_module.usage_series(
            days=7, user_id="bad-uuid", db=db, admin=admin_user
        )
        assert empty == []
