"""Wiki 双链邻居扩展召回测试（含隔离与回退）。"""

import uuid

from app.connectors.obsidian.retrieval import expand_neighbors
from app.core.config import settings
from app.models import Chunk, Document, User, WikiLink, WikiPage, WikiSpace
from app.rag.retriever import RetrievedChunk


async def _seed(db, uid: uuid.UUID, *, with_link: bool = True) -> tuple[uuid.UUID, uuid.UUID]:
    """建两个页面 A/B（A→B 双链）及各自分块，返回 (doc_a, doc_b)。"""
    space = WikiSpace(owner_id=uid, name="s", source_type="upload", root_path="/tmp/x")
    db.add(space)
    await db.flush()
    doc_a = Document(user_id=uid, title="A", source_type="wiki", status="ready")
    doc_b = Document(user_id=uid, title="B", source_type="wiki", status="ready")
    db.add_all([doc_a, doc_b])
    await db.flush()
    page_a = WikiPage(
        user_id=uid, space_id=space.id, rel_path="A.md", title="A", slug="a",
        document_id=doc_a.id,
    )
    page_b = WikiPage(
        user_id=uid, space_id=space.id, rel_path="B.md", title="B", slug="b",
        document_id=doc_b.id,
    )
    db.add_all([page_a, page_b])
    await db.flush()
    if with_link:
        db.add(
            WikiLink(
                user_id=uid, space_id=space.id, source_page_id=page_a.id,
                target_slug="b", target_page_id=page_b.id,
            )
        )
    db.add(Chunk(document_id=doc_a.id, chunk_index=0, content="A内容", meta={}))
    db.add(Chunk(document_id=doc_b.id, chunk_index=0, content="B邻居内容", meta={}))
    await db.commit()
    return doc_a.id, doc_b.id


async def _new_user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    db.add(User(id=uid, username=f"u{uid.hex[:10]}", password_hash=""))
    await db.commit()
    return uid


async def test_expand_adds_linked_neighbor(db_session, monkeypatch):
    monkeypatch.setattr(settings, "WIKI_EXPAND_NEIGHBORS", 2)
    monkeypatch.setattr(settings, "RAG_RERANK_ENABLED", False)
    uid = await _new_user(db_session)
    doc_a, _ = await _seed(db_session, uid)

    base = [
        RetrievedChunk(
            chunk_id="c1", content="A内容", meta={}, score=0.9, document_id=str(doc_a)
        )
    ]
    out = await expand_neighbors(db_session, uid, base, "问题", 5)
    assert "B邻居内容" in [c.content for c in out]


async def test_expand_noop_without_links(db_session, monkeypatch):
    monkeypatch.setattr(settings, "WIKI_EXPAND_NEIGHBORS", 2)
    uid = await _new_user(db_session)
    doc_a, _ = await _seed(db_session, uid, with_link=False)
    base = [
        RetrievedChunk(
            chunk_id="c1", content="A内容", meta={}, score=0.9, document_id=str(doc_a)
        )
    ]
    out = await expand_neighbors(db_session, uid, base, "问题", 5)
    assert [c.content for c in out] == ["A内容"]


async def test_expand_disabled_by_limit_zero(db_session, monkeypatch):
    monkeypatch.setattr(settings, "WIKI_EXPAND_NEIGHBORS", 0)
    uid = await _new_user(db_session)
    doc_a, _ = await _seed(db_session, uid)
    base = [
        RetrievedChunk(
            chunk_id="c1", content="A内容", meta={}, score=0.9, document_id=str(doc_a)
        )
    ]
    out = await expand_neighbors(db_session, uid, base, "问题", 5)
    assert [c.content for c in out] == ["A内容"]


async def test_expand_isolates_other_users(db_session, monkeypatch):
    """他人页面的链接/分块不得被扩展进来。"""
    monkeypatch.setattr(settings, "WIKI_EXPAND_NEIGHBORS", 5)
    monkeypatch.setattr(settings, "RAG_RERANK_ENABLED", False)
    uid = await _new_user(db_session)
    other = await _new_user(db_session)
    doc_a, _ = await _seed(db_session, uid)
    await _seed(db_session, other)  # 另一用户的页面与链接

    base = [
        RetrievedChunk(
            chunk_id="c1", content="A内容", meta={}, score=0.9, document_id=str(doc_a)
        )
    ]
    out = await expand_neighbors(db_session, uid, base, "问题", 5)
    assert "B邻居内容" in [c.content for c in out]  # 自己的邻居在
    # 他人内容不应因链接被误加（他人 doc 内容同为 A内容/B邻居内容，用数量约束）
    # 只应包含：自己的 A + 自己的 B = 2 条
    assert len(out) <= 2
