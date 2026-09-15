"""软删除与回收站测试（AGENTS §13：删除只标记、可恢复、检索过滤）。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.constants import DEFAULT_USER_ID
from app.main import app
from app.models import Chunk, Document
from app.rag.retriever import _bm25_search


async def test_todo_soft_delete_list_trash_restore(authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/todos", json={"title": "软删除测试"}, headers=authed_headers
        )
        tid = created.json()["data"]["id"]

        deleted = await client.delete(f"/api/v1/todos/{tid}", headers=authed_headers)
        assert deleted.status_code == 200
        assert deleted.json()["data"]["soft"] is True

        listed = (await client.get("/api/v1/todos", headers=authed_headers)).json()["data"]
        assert all(t["id"] != tid for t in listed["items"])  # 列表已过滤

        trash = (await client.get("/api/v1/trash", headers=authed_headers)).json()["data"]
        assert any(i["type"] == "todo" and i["id"] == tid for i in trash)

        restored = await client.post(
            f"/api/v1/trash/todo/{tid}/restore", headers=authed_headers
        )
        assert restored.status_code == 200
        listed = (await client.get("/api/v1/todos", headers=authed_headers)).json()["data"]
        assert any(t["id"] == tid for t in listed["items"])  # 恢复可见


async def test_bm25_excludes_soft_deleted(db_session):
    """BM25 召回必须排除已软删除的文档/分块。"""
    uid = DEFAULT_USER_ID
    doc = Document(user_id=uid, title="已删文档", source_type="md", status="ready")
    db_session.add(doc)
    await db_session.flush()
    db_session.add(Chunk(document_id=doc.id, chunk_index=0, content="独特关键词ABC", meta={}))
    await db_session.commit()

    hits = await _bm25_search(db_session, "独特关键词ABC", 5, user_id=str(uid))
    assert hits  # 未删时能召回

    # 软删除文档 → 不再召回
    from datetime import UTC, datetime

    doc.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    await db_session.commit()
    hits = await _bm25_search(db_session, "独特关键词ABC", 5, user_id=str(uid))
    assert hits == []


async def test_memory_soft_delete_excluded_and_trash(db_session, make_user):
    from app.core.soft_delete import soft_delete
    from app.models import MemoryFact

    uid = await make_user()
    row = MemoryFact(user_id=uid, fact="软删除记忆", category="fact")
    db_session.add(row)
    await db_session.commit()
    await soft_delete(db_session, row, uid)

    still = (await db_session.scalars(select(MemoryFact))).all()
    assert still and still[0].deleted_at is not None  # 仅标记，未物理删
    assert still[0].deleted_by == uid


# ---------------- 文档软删除 + 回收站（Fake 嵌入，不触网） ----------------

import hashlib

import pytest

from app.api.routes import documents as docs_module
from app.rag.vector_store import VectorStore


class _FakeEmbeddings:
    dim = 8

    async def embed(self, texts):
        out = []
        for text in texts:
            digest = hashlib.md5(text.encode()).hexdigest()
            out.append([float(int(digest[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)])
        return out


@pytest.fixture
def fake_rag(monkeypatch, tmp_path):
    store = VectorStore(dimension=8)
    monkeypatch.setattr(docs_module, "get_embedding_service", lambda: _FakeEmbeddings())
    monkeypatch.setattr(docs_module, "get_vector_store", lambda: store)
    monkeypatch.setattr(docs_module, "_DATA_DIR", tmp_path / "data")
    return store


async def test_document_soft_delete_and_restore(authed_headers, fake_rag):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        up = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.md", b"# A\n\nsoft delete body", "text/markdown")},
            headers=authed_headers,
        )
        assert up.status_code == 200, up.text
        did = up.json()["data"]["id"]

        deleted = await client.delete(f"/api/v1/documents/{did}", headers=authed_headers)
        assert deleted.status_code == 200
        assert deleted.json()["data"]["soft"] is True
        listed = (await client.get("/api/v1/documents", headers=authed_headers)).json()["data"]
        assert all(d["id"] != did for d in listed["items"])

        trash = (await client.get("/api/v1/trash", headers=authed_headers)).json()["data"]
        assert any(i["type"] == "document" and i["id"] == did for i in trash)

        restored = await client.post(
            f"/api/v1/trash/document/{did}/restore", headers=authed_headers
        )
        assert restored.status_code == 200
        listed = (await client.get("/api/v1/documents", headers=authed_headers)).json()["data"]
        assert any(d["id"] == did for d in listed["items"])


async def test_trash_error_cases(authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad_type = await client.post(
            "/api/v1/trash/unknown/x/restore", headers=authed_headers
        )
        assert bad_type.status_code == 400
        missing = await client.post(
            f"/api/v1/trash/todo/{uuid.uuid4()}/restore", headers=authed_headers
        )
        assert missing.status_code == 404


async def test_soft_delete_restore_helper(db_session, make_user):
    from app.core.soft_delete import restore, soft_delete
    from app.models import Todo

    uid = await make_user()
    todo = Todo(user_id=uid, title="helper")
    db_session.add(todo)
    await db_session.commit()

    await soft_delete(db_session, todo, uid)
    assert todo.deleted_at is not None and todo.deleted_by == uid
    await restore(db_session, todo)
    assert todo.deleted_at is None and todo.deleted_by is None
