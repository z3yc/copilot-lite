"""会话管理、Todo REST 与文档详情接口测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import Base, async_session_factory, engine
from app.main import app


async def _setup_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_document_detail_chunks() -> None:
    """文档详情：返回分块列表与标题路径。"""
    await _setup_tables()
    from app.core.constants import DEFAULT_USER_ID
    from app.models import Chunk, Document

    async with async_session_factory() as db:
        doc = Document(user_id=DEFAULT_USER_ID, title="测试.md", source_type="md", status="ready")
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        db.add(
            Chunk(
                document_id=doc.id,
                chunk_index=0,
                content="分块内容A",
                meta={"headings": ["第一章"]},
            )
        )
        await db.commit()
        doc_id = str(doc.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/api/v1/documents/{doc_id}/chunks")
        assert r.status_code == 200
        data = r.json()
        assert data["chunk_count"] == 1
        assert data["chunks"][0]["headings"] == ["第一章"]
        assert data["chunks"][0]["content"] == "分块内容A"


@pytest.mark.asyncio
async def test_sessions_crud() -> None:
    """会话列表 / 历史消息 / 删除。"""
    await _setup_tables()
    from app.core.constants import DEFAULT_USER_ID
    from app.models import ChatSession, Message

    async with async_session_factory() as db:
        s = ChatSession(user_id=DEFAULT_USER_ID, title="测试会话")
        db.add(s)
        await db.commit()
        await db.refresh(s)
        db.add(Message(session_id=s.id, role="user", content="第一条"))
        db.add(Message(session_id=s.id, role="assistant", content="回复"))
        await db.commit()
        sid = str(s.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 列表
        r = await client.get("/api/v1/sessions")
        assert r.status_code == 200
        assert any(x["id"] == sid for x in r.json())

        # 历史消息
        r = await client.get(f"/api/v1/sessions/{sid}/messages")
        assert r.status_code == 200
        roles = [m["role"] for m in r.json()]
        assert roles == ["user", "assistant"]

        # 删除
        r = await client.delete(f"/api/v1/sessions/{sid}")
        assert r.status_code == 200
        r = await client.get(f"/api/v1/sessions/{sid}/messages")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_todos_api_crud() -> None:
    """Todo REST：创建/列表/完成/删除。"""
    await _setup_tables()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 创建
        r = await client.post(
            "/api/v1/todos", json={"title": "学习 React", "priority": 1}
        )
        assert r.status_code == 200
        tid = r.json()["id"]
        assert r.json()["status"] == "pending"

        # 列表
        r = await client.get("/api/v1/todos")
        assert r.status_code == 200
        assert any(x["id"] == tid for x in r.json())

        # 完成
        r = await client.patch(f"/api/v1/todos/{tid}", json={"status": "done"})
        assert r.json()["status"] == "done"

        # 删除
        r = await client.delete(f"/api/v1/todos/{tid}")
        assert r.status_code == 200
