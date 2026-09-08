"""混合检索：向量语义检索 + BM25 关键词检索 + RRF 融合 + Rerank 精排。

为什么混合（面试必讲）：
- 纯向量检索对专有名词/代码符号/ID 等"字面匹配"场景召回差；
- BM25 关键词检索语义泛化弱，但字面命中精准；
- RRF（Reciprocal Rank Fusion）按排名倒数融合两路结果，无需调权重；
- 融合出候选后，用交叉编码器（bge-reranker）精排——query×passage 深度交互打分，
  比双塔相似度更精准，取前 N 注入 LLM（配置开关可对比效果）。

当前 BM25 为轻量实现（PostgreSQL ILIKE + 命中词数打分），
个人知识库规模足够；大规模场景可平滑替换为
PostgreSQL FTS / Elasticsearch（接口不变）。
"""

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Chunk
from app.rag.embeddings import EmbeddingService
from app.rag.reranker import Reranker, get_reranker
from app.rag.vector_store import SearchHit, VectorStore

try:  # 可选分词依赖：未安装时退化逐字切分
    import jieba as _jieba
except ImportError:  # pragma: no cover - 运行环境已安装 jieba
    _jieba = None

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
    """查询词提取：中文用 jieba 分词（多字词召回优于逐字），英文单词整体。

    jieba 不可用时退化为逐字切分（英文单词整体 + 中文逐字），行为可预期。
    """
    raw = [t for t in _TOKEN_RE.findall(query) if t.strip()]
    if _jieba is not None:
        zh_runs = re.findall(r"[\u4e00-\u9fff]+", query)
        if zh_runs:
            words: list[str] = []
            for run in zh_runs:
                words.extend(w for w in _jieba.lcut(run) if w.strip())
            non_zh = [t for t in raw if not re.fullmatch(r"[\u4e00-\u9fff]+", t)]
            return words + non_zh
    return raw


async def _bm25_search(
    db: AsyncSession, query: str, top_k: int, user_id=None
) -> list[SearchHit]:
    """轻量 BM25：OR 召回含任一查询词的块，按命中词数占比打分。

    user_id 提供时仅检索该用户的分块（多用户数据隔离，
    需 JOIN documents 表按归属过滤）。
    """
    from sqlalchemy import or_

    from app.models import Document

    terms = _tokenize(query)
    if not terms:
        return []

    conditions = [Chunk.content.ilike(f"%{term}%") for term in terms[:12]]
    stmt = select(Chunk)
    if user_id:
        stmt = stmt.join(Document, Chunk.document_id == Document.id).where(
            Document.user_id == uuid.UUID(str(user_id))
        )
    stmt = stmt.where(or_(*conditions)).limit(top_k * 5)
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


async def _rerank_candidates(
    reranker: Reranker,
    query: str,
    candidates: list[RetrievedChunk],
    top_n: int,
) -> list[RetrievedChunk]:
    """按精排分数重排候选（分数覆盖为交叉编码器得分）。"""
    if len(candidates) <= 1:
        return candidates
    passages = [c.content for c in candidates]
    ranked = await reranker.rerank(query, passages, top_n)
    merged = []
    for index, score in ranked:
        c = candidates[index]
        merged.append(
            RetrievedChunk(
                chunk_id=c.chunk_id,
                content=c.content,
                meta=c.meta,
                score=score,
            )
        )
    return merged


async def hybrid_search(
    db: AsyncSession,
    query: str,
    embeddings: EmbeddingService,
    vector_store: VectorStore,
    top_k: int = settings.RAG_TOP_K,
    candidate_k: int = settings.RAG_RERANK_CANDIDATE_K,
    rerank_top_n: int = settings.RAG_RERANK_TOP_N,
    document_id: str | None = None,
    user_id: str | None = None,
    reranker: Reranker | None = None,
) -> list[RetrievedChunk]:
    """混合检索主入口：向量 + BM25 → RRF 融合 → Rerank 精排 → 前 N 注入。

    user_id 提供时两路检索均限定在该用户范围内（多用户数据隔离）；
    reranker 缺省时按配置取全局单例；开关 `RAG_RERANK_ENABLED` 关闭时
    退化为纯融合截断（与旧版行为一致），便于 A/B 对比效果。
    """
    # 1. 向量检索
    qvec = (await embeddings.embed([query]))[0]
    vector_hits = await vector_store.search(
        qvec, top_k, document_id=document_id, user_id=user_id
    )

    # 2. BM25 关键词检索
    keyword_hits = await _bm25_search(db, query, top_k, user_id=user_id)

    # 3. RRF 融合 → candidate_k 条候选（保留足够候选供精排）
    candidates = _rrf_fuse(vector_hits, keyword_hits, candidate_k)

    # 4. Rerank 精排：交叉编码器对 query×passage 逐对打分，取前 N
    if settings.RAG_RERANK_ENABLED:
        if reranker is None:
            reranker = get_reranker()
        merged = await _rerank_candidates(reranker, query, candidates, rerank_top_n)
    else:
        merged = candidates[:rerank_top_n]

    logger.info(
        "混合检索: query=%s 向量=%d BM25=%d 候选=%d 精排=%d (rerank=%s)",
        query[:20], len(vector_hits), len(keyword_hits), len(candidates), len(merged),
        settings.RAG_RERANK_ENABLED,
    )
    return merged


async def multi_query_search(
    db: AsyncSession,
    queries: list[str],
    embeddings: EmbeddingService,
    vector_store: VectorStore,
    top_k: int = settings.RAG_TOP_K,
    candidate_k: int = settings.RAG_RERANK_CANDIDATE_K,
    rerank_top_n: int = settings.RAG_RERANK_TOP_N,
    document_id: str | None = None,
    user_id: str | None = None,
    reranker: Reranker | None = None,
) -> list[RetrievedChunk]:
    """多查询召回：对每个改写分别混合检索，再跨查询 RRF 融合。

    单查询内部已完成 BM25+向量 RRF + Rerank；跨查询融合让
    "被某个改写命中、但原始问题未命中"的文档也有机会进入最终结果
    （multi-query 是补召回率的经典手段）。
    """
    if not queries:
        return []
    hit_lists = [
        await hybrid_search(
            db, q, embeddings, vector_store,
            top_k=top_k, candidate_k=candidate_k, rerank_top_n=rerank_top_n,
            document_id=document_id, user_id=user_id, reranker=reranker,
        )
        for q in queries
    ]

    # 跨查询 RRF：同一 chunk 在不同查询的排名倒数求和
    scores: dict[str, tuple[float, RetrievedChunk]] = {}
    for hits in hit_lists:
        for rank, h in enumerate(hits, start=1):
            if h.chunk_id in scores:
                s, _ = scores[h.chunk_id]
                scores[h.chunk_id] = (s + 1.0 / (RRF_K + rank), h)
            else:
                scores[h.chunk_id] = (1.0 / (RRF_K + rank), h)
    merged = [
        RetrievedChunk(chunk_id=h.chunk_id, content=h.content, meta=h.meta, score=s)
        for s, h in sorted(scores.values(), key=lambda item: item[0], reverse=True)
    ]
    return merged[:rerank_top_n]
