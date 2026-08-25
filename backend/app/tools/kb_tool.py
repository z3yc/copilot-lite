"""知识库检索工具：让 Agent 具备"从个人知识库找答案"的能力。

通过 ToolRegistry 注册，Agent 在用户问题涉及文档/笔记/资料时自动调用。
返回带来源（文档标题/标题路径/页码）的片段，供主 Agent 生成带引用的回答。
"""

import json

from app.rag import get_embedding_service, get_vector_store, hybrid_search
from app.tools.base import ToolContext, registry


@registry.register
async def kb_search(ctx: ToolContext, query: str, top_k: int = 3) -> str:
    """在个人知识库中检索与问题最相关的文档片段，返回带来源的内容（含文档标题、章节、页码）。"""
    top_k = max(1, min(5, top_k))
    results = await hybrid_search(
        db=ctx.session,
        query=query,
        embeddings=get_embedding_service(),
        vector_store=get_vector_store(),
        top_k=top_k,
    )
    payload = []
    for r in results:
        meta = r.meta or {}
        headings = meta.get("headings") or []
        title = meta.get("document_title", "未知文档")
        source = title
        if headings:
            source += " > " + " > ".join(headings)
        if meta.get("page"):
            source += f"（第{meta['page']}页）"
        payload.append({"来源": source, "内容": r.content[:500]})
    return json.dumps(payload, ensure_ascii=False)
