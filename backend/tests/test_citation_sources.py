"""引用构造：来源类型标签（Wiki / 文档）+ 可跳转身份。"""

import uuid

from app.rag.citations import build_citation, build_source_label
from app.rag.retriever import RetrievedChunk


def _chunk(meta: dict, document_id: str = "d1") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1", content="正文内容", meta=meta, score=0.5, document_id=document_id
    )


def test_wiki_label_from_origin():
    """连接器提供身份时：类型为 wiki，标签带空间名与页面名。"""
    kind, label = build_source_label(
        {"document_title": "方法论"},
        {"kind": "wiki", "space_name": "我的笔记", "title": "方法论"},
    )
    assert kind == "wiki"
    assert label == "Wiki / 我的笔记 / 方法论"


def test_wiki_label_falls_back_to_chunk_meta():
    """身份缺失（页面行已软删/重建）时回退 chunk meta 快照。"""
    kind, label = build_source_label({"wiki_space": "我的笔记", "wiki_title": "方法论"}, None)
    assert (kind, label) == ("wiki", "Wiki / 我的笔记 / 方法论")


def test_document_label_with_headings_and_page():
    """文档来源：带标题路径与页码。"""
    kind, label = build_source_label(
        {"document_title": "学习笔记.md", "headings": ["第一章", "第一节"], "page": 3},
        None,
    )
    assert (kind, label) == ("document", "文档 / 学习笔记.md / 第一章 > 第一节 / 第 3 页")


def test_document_label_without_headings_and_page():
    """文档来源：无标题路径与页码时省略（不留空分隔符）。"""
    kind, label = build_source_label({"document_title": "报告.pdf"}, None)
    assert (kind, label) == ("document", "文档 / 报告.pdf")


def test_wiki_citation_carries_navigation():
    """Wiki 引用带可跳转身份（page_id / space_id）。"""
    cite = build_citation(
        1,
        _chunk({"wiki_space": "我的笔记", "wiki_title": "方法论"}),
        {
            "kind": "wiki",
            "page_id": "p1",
            "space_id": "s1",
            "space_name": "我的笔记",
            "rel_path": "笔记/方法论.md",
            "title": "方法论",
        },
    )
    assert cite["source"] == "Wiki / 我的笔记 / 方法论"
    assert cite["source_kind"] == "wiki"
    assert cite["wiki"] == {
        "page_id": "p1",
        "space_id": "s1",
        "space_name": "我的笔记",
        "rel_path": "笔记/方法论.md",
    }
    assert cite["index"] == 1 and cite["chunk_id"] == "c1" and cite["document_id"] == "d1"
    assert cite["snippet"] == "正文内容"


def test_wiki_fallback_has_no_navigation():
    """meta 兜底得到的 wiki 标签不提供跳转对象（页面行已不可用）。"""
    cite = build_citation(1, _chunk({"wiki_space": "我的笔记", "wiki_title": "方法论"}), None)
    assert cite["source_kind"] == "wiki"
    assert "wiki" not in cite


def test_document_citation_page_none_when_absent():
    """文档无页码时 page 为 None（契约字段恒存在）。"""
    cite = build_citation(2, _chunk({"document_title": "报告.pdf"}), None)
    assert cite["source"] == "文档 / 报告.pdf"
    assert cite["source_kind"] == "document"
    assert cite["page"] is None


# ---------------- 连接器来源身份汇总 ----------------


class _GoodConnector:
    name = "good"

    async def describe_sources(self, db, user_id, document_ids):
        return {"d1": {"kind": "wiki", "page_id": "p1"}}


class _BoomConnector:
    name = "boom"

    async def describe_sources(self, db, user_id, document_ids):
        raise RuntimeError("连接器故障")


async def test_collect_source_meta_merges_and_tolerates_failure(monkeypatch):
    """汇总来源身份：单个连接器故障不拖垮整体（增强不能拖垮主链路）。"""
    from app.connectors import base as base_module

    monkeypatch.setattr(
        base_module, "_REGISTRY", {"good": _GoodConnector(), "boom": _BoomConnector()}
    )
    merged = await base_module.collect_source_meta(object(), "u1", ["d1"])
    assert merged["d1"]["page_id"] == "p1"


async def test_collect_source_meta_skips_without_session_or_ids():
    """无 db 或无事发文档时零成本返回（不查库）。"""
    from app.connectors import base as base_module

    assert await base_module.collect_source_meta(None, "u1", ["d1"]) == {}
    assert await base_module.collect_source_meta(object(), "u1", []) == {}


async def test_default_connector_has_no_source_identity():
    """SourceConnector 默认不提供来源身份（可选能力，连接器按需覆写）。"""
    from app.connectors.base import SourceConnector

    class _Bare(SourceConnector):
        name = "bare"

        async def create_space(self, db, user_id, name, *, server_path=None, source_type=None):
            return None

        async def import_archive(self, db, user_id, space, data):
            return 0

        async def import_files(self, db, user_id, space, items):
            return 0

        async def sync(self, db, user_id, space):
            return {}

    assert await _Bare().describe_sources(object(), "u1", ["d1"]) == {}


# ---------------- Obsidian 来源身份解析 ----------------


async def _new_user(db) -> uuid.UUID:
    from app.models import User

    uid = uuid.uuid4()
    db.add(User(id=uid, username=f"u{uid.hex[:10]}", password_hash=""))
    await db.commit()
    return uid


async def _wiki_doc(db, uid, title: str = "方法论"):
    from app.models import Document

    doc = Document(user_id=uid, title=title, source_type="wiki", status="ready")
    db.add(doc)
    await db.commit()
    return doc


async def test_obsidian_describe_sources_returns_wiki_identity(db_session):
    """命中 Wiki 页面时返回空间/页面身份（含可跳转 page_id）。"""
    from app.connectors.obsidian import service as wiki_service
    from app.models import WikiPage, WikiSpace

    uid = await _new_user(db_session)
    space = WikiSpace(owner_id=uid, name="我的笔记", source_type="upload", root_path="/tmp/x")
    db_session.add(space)
    await db_session.flush()
    doc = await _wiki_doc(db_session, uid)
    page = WikiPage(
        user_id=uid,
        space_id=space.id,
        rel_path="笔记/方法论.md",
        title="方法论",
        slug="方法论",
        document_id=doc.id,
    )
    db_session.add(page)
    await db_session.commit()

    meta = await wiki_service.describe_sources(db_session, uid, [str(doc.id)])
    origin = meta[str(doc.id)]
    assert origin["kind"] == "wiki"
    assert origin["page_id"] == str(page.id)
    assert origin["space_id"] == str(space.id)
    assert origin["space_name"] == "我的笔记"
    assert origin["rel_path"] == "笔记/方法论.md"
    assert origin["title"] == "方法论"


async def test_obsidian_describe_sources_filters_other_user_deleted_and_bad_input(db_session):
    """跨用户/缺 user_id/页面软删/非法 id 一律不返回身份（AGENTS §6.3/§13）。"""
    from app.connectors.obsidian import service as wiki_service
    from app.core.soft_delete import soft_delete
    from app.models import WikiPage, WikiSpace

    owner = await _new_user(db_session)
    other = await _new_user(db_session)
    space = WikiSpace(owner_id=owner, name="私有", source_type="upload", root_path="/tmp/y")
    db_session.add(space)
    await db_session.flush()
    doc = await _wiki_doc(db_session, owner, title="私密")
    page = WikiPage(
        user_id=owner,
        space_id=space.id,
        rel_path="a.md",
        title="私密",
        slug="a",
        document_id=doc.id,
    )
    db_session.add(page)
    await db_session.commit()

    # 跨用户：无权者拿不到任何身份
    assert await wiki_service.describe_sources(db_session, other, [str(doc.id)]) == {}
    # user_id 缺失：fail-closed
    assert await wiki_service.describe_sources(db_session, None, [str(doc.id)]) == {}
    # 非法 document_id 不抛错
    assert await wiki_service.describe_sources(db_session, owner, ["not-a-uuid"]) == {}
    # 页面软删：不再提供身份（标签侧由 chunk meta 兜底）
    await soft_delete(db_session, page, owner)
    assert await wiki_service.describe_sources(db_session, owner, [str(doc.id)]) == {}
    # 空间软删：同样不提供
    await db_session.refresh(page)
    page.deleted_at = None
    await db_session.commit()
    await soft_delete(db_session, space, owner)
    assert await wiki_service.describe_sources(db_session, owner, [str(doc.id)]) == {}
