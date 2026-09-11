"""Obsidian 双链邻居扩展召回（G-M2）。

命中页的 1-hop 链接页（出链 + 入链）各取一个代表块作为候选，与原始命中一起
交给交叉编码器精排——补"答案在关联页、但与问题字面不相似"的召回缺口。

失败一律回退原结果（增强功能不得拖垮主检索链路）。
"""

import logging
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Chunk, WikiLink, WikiPage
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def expand_neighbors(
    db: AsyncSession,
    user_id,
    results: list[RetrievedChunk],
    query: str,
    top_n: int,
) -> list[RetrievedChunk]:
    """用双链邻居扩展候选并精排，返回前 top_n；任何异常回退原结果。"""
    try:
        uid = _as_uuid(user_id)
        doc_ids = [uuid.UUID(r.document_id) for r in results if r.document_id]
        if not doc_ids:
            return results

        pages = (
            await db.scalars(
                select(WikiPage).where(
                    WikiPage.user_id == uid, WikiPage.document_id.in_(doc_ids)
                )
            )
        ).all()
        if not pages:
            return results
        page_ids = {p.id for p in pages}

        links = (
            await db.scalars(
                select(WikiLink).where(
                    WikiLink.user_id == uid,
                    or_(
                        WikiLink.source_page_id.in_(page_ids),
                        WikiLink.target_page_id.in_(page_ids),
                    ),
                )
            )
        ).all()
        neighbor_ids: set[uuid.UUID] = set()
        for link in links:
            if link.source_page_id in page_ids and link.target_page_id:
                neighbor_ids.add(link.target_page_id)  # 出链：命中页 → 邻居
            if link.target_page_id in page_ids:
                neighbor_ids.add(link.source_page_id)  # 入链：邻居 → 命中页
        neighbor_ids -= page_ids

        limit = max(0, settings.WIKI_EXPAND_NEIGHBORS)
        if not neighbor_ids or limit == 0:
            return results

        neighbor_pages = (
            await db.scalars(
                select(WikiPage).where(
                    WikiPage.id.in_(list(neighbor_ids)), WikiPage.user_id == uid
                )
            )
        ).all()[:limit]

        merged = list(results)
        for page in neighbor_pages:
            if not page.document_id:
                continue
            chunk = await db.scalar(
                select(Chunk)
                .where(Chunk.document_id == page.document_id)
                .order_by(Chunk.chunk_index)
                .limit(1)
            )
            if chunk is None:
                continue
            merged.append(
                RetrievedChunk(
                    chunk_id=str(chunk.id),
                    content=chunk.content,
                    meta=chunk.meta or {},
                    score=0.0,
                    document_id=str(page.document_id),
                )
            )
        if len(merged) == len(results):
            return results  # 未补充到有效邻居

        if settings.RAG_RERANK_ENABLED and len(merged) > 1:
            try:
                from app.rag.reranker import get_reranker

                ranked = await get_reranker().rerank(
                    query, [c.content for c in merged], top_n
                )
                return [
                    RetrievedChunk(
                        chunk_id=merged[i].chunk_id,
                        content=merged[i].content,
                        meta=merged[i].meta,
                        score=score,
                        document_id=merged[i].document_id,
                    )
                    for i, score in ranked
                ]
            except Exception:
                logger.warning("Wiki 邻居扩展精排失败，回退原结果", exc_info=True)
                return results

        merged.sort(key=lambda c: c.score, reverse=True)
        return merged[:top_n]
    except Exception:
        logger.warning("Wiki 邻居扩展失败，回退原结果", exc_info=True)
        return results
