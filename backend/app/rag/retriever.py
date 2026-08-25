"""混合检索：向量语义检索 + BM25 关键词检索 + RRF 融合。

为什么混合（面试必讲）：
- 纯向量检索对专有名词/代码符号/ID 等"字面匹配"场景召回差；
- BM25 关键词检索语义泛化弱，但字面命中精准；
- RRF（Reciprocal Rank Fusion）按排名倒数融合两路结果，无需调权重。

当前 BM25 为轻量实现（PostgreSQL ILIKE + 命中词数打分），
个人知识库规模足够；大规模场景可平滑替换为
PostgreSQL FTS / Elasticsearch（接口不变）。
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Chunk
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import SearchHit, VectorStore

logger = logging.getLogger(__name__)

RRF_K = 60  # RRF 平滑常数

# 匹配英文/数字单词 + 中文字符（中文逐字作为检索词）
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


@dataclass
class RetrievedChunk:
    """最终检索结果（供 RAG 生成与引用溯源）。"""

    chunk_id: str
    content: str
    meta: dict
    score: float


def _tokenize(query: str) -> list[str]:
    """查询词提取：英文单词整体，中文逐字。"""
    return [t for t in _TOKEN_RE.findall(query) if t.strip()]


async def _bm25_search(db: AsyncSession, query: str, top_k: int) -> list[SearchHit]:
    """轻量 BM25：OR 召回含任一查询词的块，按命中词数占比打分。"""
    from sqlalchemy import or_

    terms = _tokenize(query)
    if not terms:
        return []

    conditions = [Chunk.content.ilike(f"%{term}%") for term in terms[:12]]
    stmt = select(Chunk).where(or_(*conditions)).limit(top_k * 5)
    rows = (await db.scalars(stmt)).all()

    hits: list[SearchHit] = []
    for row in rows:
        # 命中词数占比作为简化 BM25 分数
        hit_terms = sum(1 for t in terms if t in row.content)
        if hit_terms == 0:
            continue
        hits.append(
            SearchHit(
                chunk_id=str(row.id),
                document_id=str(row.document_id),
                content=row.content,
                score=hit_terms / len(terms),
                meta=row.meta,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


def _rrf_fuse(
    vector_hits: list[SearchHit],
    keyword_hits: list[SearchHit],
    top_k: int,
) -> list[RetrievedChunk]:
    """RRF 融合：score = Σ 1/(k + rank)。"""
    scores: dict[str, tuple[float, str, dict]] = {}

    def add(hits: list[SearchHit]) -> None:
        for rank, h in enumerate(hits, start=1):
            key = h.chunk_id
            if key in scores:
                scores[key][0] += 1.0 / (RRF_K + rank)
            else:
                scores[key] = [1.0 / (RRF_K + rank), h.content, h.meta]

    add(vector_hits)
    add(keyword_hits)

    merged = [
        RetrievedChunk(chunk_id=k, content=v[1], meta=v[2], score=v[0])
        for k, v in scores.items()
    ]
    merged.sort(key=lambda c: c.score, reverse=True)
    return merged[:top_k]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    embeddings: EmbeddingService,
    vector_store: VectorStore,
    top_k: int = settings.RAG_TOP_K,
    rerank_top_k: int = settings.RAG_RERANK_TOP_K,
    document_id: str | None = None,
) -> list[RetrievedChunk]:
    """混合检索主入口：向量 + BM25 → RRF 融合 → 截断精排。"""
    # 1. 向量检索
    qvec = (await embeddings.embed([query]))[0]
    vector_hits = await vector_store.search(qvec, top_k, document_id=document_id)

    # 2. BM25 关键词检索
    keyword_hits = await _bm25_search(db, query, top_k)

    # 3. RRF 融合（重排）
    merged = _rrf_fuse(vector_hits, keyword_hits, rerank_top_k)
    logger.info(
        "混合检索: query=%s 向量=%d BM25=%d 融合=%d",
        query[:20], len(vector_hits), len(keyword_hits), len(merged),
    )
    return merged
