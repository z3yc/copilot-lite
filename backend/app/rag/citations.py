"""引用构造：把检索结果 + 来源身份格式化为可展示、可跳转的引用。

来源身份由连接器提供（`SourceConnector.describe_sources`），本模块**不含具体来源知识**：
只做「类型判定 → 标签格式化 → 契约字段拼装」，保证引用展示口径唯一
（AGENTS §12 连接器收口：接新来源不改工具层）。

类型判定优先级：
1. 连接器身份（Wiki 等，含导航目标）；
2. chunk meta 快照（`wiki_space`/`wiki_title`）——页面行已软删/重建时标签仍正确，仅不可跳；
3. 普通文档（标题 + 标题路径 + 页码）。
"""

WIKI_KIND = "wiki"
DOC_KIND = "document"

_MAX_SNIPPET = 160


def build_source_label(meta: dict, origin: dict | None) -> tuple[str, str]:
    """返回 (source_kind, 展示标签)。"""
    meta = meta or {}
    if origin and origin.get("kind") == WIKI_KIND:
        parts = ["Wiki", str(origin.get("space_name") or ""), str(origin.get("title") or "")]
        return WIKI_KIND, " / ".join(p for p in parts if p)

    wiki_space = meta.get("wiki_space")
    wiki_title = meta.get("wiki_title")
    if wiki_space or wiki_title:
        parts = [
            "Wiki",
            str(wiki_space or ""),
            str(wiki_title or meta.get("document_title") or ""),
        ]
        return WIKI_KIND, " / ".join(p for p in parts if p)

    parts = ["文档", str(meta.get("document_title") or "未知文档")]
    headings = meta.get("headings") or []
    if headings:
        parts.append(" > ".join(str(h) for h in headings))
    if isinstance(meta.get("page"), int):
        parts.append(f"第 {meta['page']} 页")
    return DOC_KIND, " / ".join(parts)


def build_citation(index: int, result, origin: dict | None = None) -> dict:
    """构造单条引用（落 `Message.extra.citations`，前端据此渲染与跳转）。"""
    meta = result.meta or {}
    kind, label = build_source_label(meta, origin)
    page = meta.get("page")
    cite: dict = {
        "index": index,
        "chunk_id": result.chunk_id,
        "document_id": result.document_id,
        "source": label,
        "source_kind": kind,
        # 文档页码；Wiki/无页码为 None（字段恒存在，便于前端类型稳定）
        "page": page if isinstance(page, int) else None,
        "snippet": result.content[:_MAX_SNIPPET],
    }
    if kind == WIKI_KIND and origin and origin.get("page_id"):
        cite["wiki"] = {
            "page_id": str(origin["page_id"]),
            "space_id": str(origin.get("space_id") or ""),
            "space_name": str(origin.get("space_name") or ""),
            "rel_path": str(origin.get("rel_path") or ""),
        }
    return cite
