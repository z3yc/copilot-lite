"""管理后台评测作业接口测试（ADMIN_PLAN §9 N1.7）。

覆盖：页面触发建作业（queued + 配置指纹）、列表/详情、畸形 id 404。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import async_session_factory
from app.main import app
from app.models import User


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_eval_run_queues_with_fingerprint(client, admin_headers) -> None:
    """建作业返回 queued 并带配置指纹（指标可比性，§2.5）。"""
    r = await client.post(
        "/api/v1/admin/eval/runs",
        json={"source_scope": "all"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "queued"
    assert data["progress"] == 0
    fp = data["config_fingerprint"]
    for key in ("engine", "embedding_model", "prompt_version", "top_k", "rerank"):
        assert key in fp


@pytest.mark.asyncio
async def test_list_and_get_eval_run(client, admin_headers) -> None:
    """列表与详情可查到刚建的作业。"""
    r = await client.post(
        "/api/v1/admin/eval/runs", json={}, headers=admin_headers
    )
    rid = r.json()["data"]["id"]

    r = await client.get("/api/v1/admin/eval/runs", headers=admin_headers)
    assert r.status_code == 200
    assert any(item["id"] == rid for item in r.json()["data"]["items"])

    r = await client.get(f"/api/v1/admin/eval/runs/{rid}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["data"]["id"] == rid


@pytest.mark.asyncio
async def test_eval_run_malformed_id_404(client, admin_headers) -> None:
    """畸形/不存在 run_id 返回 404。"""
    r = await client.get("/api/v1/admin/eval/runs/not-a-uuid", headers=admin_headers)
    assert r.status_code == 404
    r = await client.get(
        f"/api/v1/admin/eval/runs/{uuid.uuid4()}", headers=admin_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_eval_run_handlers_direct(db_session, admin_headers) -> None:
    """直接调用 handler：覆盖建作业/列表/详情各分支。"""
    from app.api.routes import admin as admin_module

    async with async_session_factory() as db:
        admin_user = await db.get(User, uuid.UUID(admin_headers["uid"]))
        run = await admin_module.create_eval_run(
            admin_module.EvalRunCreateRequest(source_scope="wiki"),
            db=db,
            admin=admin_user,
        )
        assert run.source_scope == "wiki"

        page = await admin_module.list_eval_runs(
            status="queued",
            source_scope=None,
            page=1,
            page_size=20,
            db=db,
            admin=admin_user,
        )
        assert page.total >= 1

        detail = await admin_module.get_eval_run(run.id, db=db, admin=admin_user)
        assert detail.id == run.id
