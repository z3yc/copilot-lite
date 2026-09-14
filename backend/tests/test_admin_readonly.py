"""管理后台只读接口测试：审计查询（N1.6）+ 知识库概览（N1.5）。"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import DEFAULT_USER_ID
from app.core.db import async_session_factory
from app.main import app
from app.models import Chunk, Document, WikiLink, WikiPage, WikiSpace


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_audit_query_filters_and_shape(client, admin_headers) -> None:
    """审计查询：可按 action 过滤，返回分页结构且含写操作记录。"""
    username = f"aud{uuid.uuid4().hex[:6]}"
    r = await client.post(
        "/api/v1/admin/users",
        json={"username": username, "password": "secret123", "role": "user"},
        headers=admin_headers,
    )
    assert r.status_code == 200

    r = await client.get(
        "/api/v1/admin/audit?action=user.create", headers=admin_headers
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["action"] == "user.create"
    assert item["resource_type"] == "user"
    assert "request_id" in item
    assert "meta" in item


@pytest.mark.asyncio
async def test_audit_query_by_request_id(client, admin_headers) -> None:
    """审计可按 request_id 串链路（过滤无匹配返回空）。"""
    r = await client.get(
        "/api/v1/admin/audit?request_id=does-not-exist", headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_knowledge_overview(client, admin_headers) -> None:
    """知识库概览：文档/chunk 总数、按来源切片、失败数、Wiki 统计。"""
    async with async_session_factory() as db:
        doc = Document(
            user_id=DEFAULT_USER_ID, title="概览测试.md", source_type="md", status="ready"
        )
        db.add(doc)
        await db.flush()
        db.add(Chunk(document_id=doc.id, chunk_index=0, content="内容", meta={}))
        failed = Document(
            user_id=DEFAULT_USER_ID, title="失败.pdf", source_type="pdf", status="failed"
        )
        db.add(failed)
        space = WikiSpace(owner_id=DEFAULT_USER_ID, name="空间A", root_path="/tmp/a")
        db.add(space)
        await db.flush()
        page = WikiPage(
            user_id=DEFAULT_USER_ID,
            space_id=space.id,
            rel_path="a.md",
            title="A",
            slug="a",
        )
        db.add(page)
        await db.flush()
        db.add(
            WikiLink(
                user_id=DEFAULT_USER_ID,
                space_id=space.id,
                source_page_id=page.id,
                target_slug="missing",
                target_page_id=None,
            )
        )
        await db.commit()

    r = await client.get("/api/v1/admin/knowledge", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["documents_total"] >= 2
    assert data["chunks_total"] >= 1
    assert data["failed_documents"] >= 1
    by_source = {s["source_type"]: s for s in data["by_source"]}
    assert by_source["md"]["chunks"] >= 1
    assert data["wiki_spaces"] >= 1
    assert data["wiki_pages"] >= 1
    assert data["wiki_dangling_links"] >= 1


@pytest.mark.asyncio
async def test_knowledge_overview_direct(db_session, admin_headers) -> None:
    """直接调用概览 handler：覆盖按来源切片与 Wiki 统计分支。"""
    from app.api.routes import admin as admin_module
    from app.models import User

    async with async_session_factory() as db:
        doc = Document(
            user_id=DEFAULT_USER_ID, title="直接.md", source_type="docx", status="ready"
        )
        db.add(doc)
        await db.flush()
        db.add(Chunk(document_id=doc.id, chunk_index=0, content="c", meta={}))
        await db.commit()

    async with async_session_factory() as db:
        admin_user = await db.get(User, uuid.UUID(admin_headers["uid"]))
        out = await admin_module.knowledge_overview(db=db, admin=admin_user)
    assert out.documents_total >= 1
    assert out.chunks_total >= 1
    assert any(s.source_type == "docx" for s in out.by_source)


@pytest.mark.asyncio
async def test_list_users_direct(db_session, admin_headers) -> None:
    """直接调用列表 handler：覆盖筛选/分页/批量 Key 查询分支。"""
    from app.api.routes import admin as admin_module
    from app.models import User

    async with async_session_factory() as db:
        admin_user = await db.get(User, uuid.UUID(admin_headers["uid"]))
        page = await admin_module.list_users(
            q=None,
            role="admin",
            status="active",
            include_deleted=False,
            page=1,
            page_size=20,
            db=db,
            admin=admin_user,
        )
        assert page.total >= 1
        assert any(u.role == "admin" for u in page.items)
