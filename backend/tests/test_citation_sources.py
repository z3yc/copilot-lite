"""引用构造：来源类型标签（Wiki / 文档）+ 可跳转身份。"""

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
