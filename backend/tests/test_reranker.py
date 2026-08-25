"""Rerank 精排测试：Fake 交叉编码器（不下载模型），验证精排链路与开关行为。

覆盖：
- Reranker 封装：排序降序 / top_n 截断 / 空与单候选短路（不加载模型）；
- get_reranker 单例（懒加载，不触发模型下载）；
- hybrid_search 链路接入：开关开启时按精排分数重排，关闭时行为与旧版一致。
"""

import hashlib
import uuid

import pytest

from app.core.config import settings
from app.core.constants import DEFAULT_USER_ID
from app.models import Chunk, Document
from app.rag.reranker import Reranker, get_reranker
from app.rag.retriever import RetrievedChunk, _rerank_candidates, hybrid_search
from app.rag.vector_store import VectorStore


class FakeEmbeddings:
    """基于文本哈希的确定性伪嵌入（维度 8）。"""

    dim = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = hashlib.md5(t.encode()).hexdigest()
            out.append([float(int(h[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)])
        return out


class FakeCrossEncoder:
    """伪交叉编码器：分数由 query+doc 内容哈希决定（确定性，便于断言顺序）。"""

    def __init__(self, fixed: list[float] | None = None) -> None:
        self._fixed = fixed

    def rerank(self, query: str, documents, batch_size: int = 64):
        if self._fixed is not None:
            return iter(self._fixed)
        return iter(self._score(query, doc) for doc in documents)

    @staticmethod
    def _score(query: str, doc: str) -> float:
        h = hashlib.md5((query + "|" + doc).encode()).hexdigest()
        return int(h[:2], 16) / 255.0


class FakeReranker(Reranker):
    """替换 _model 的 Reranker，避免导入/加载真实模型。"""

    def __init__(self, fixed: list[float] | None = None) -> None:
        super().__init__(model_name="fake")
        self._model = FakeCrossEncoder(fixed)


class RaisingReranker(Reranker):
    """rerank 被调用即失败（用于断言开关关闭时不会触发精排）。"""

    def __init__(self) -> None:
        super().__init__(model_name="fake")
        self.calls = 0

    async def rerank(self, query: str, passages: list[str], top_n: int):
        self.calls += 1
        raise AssertionError("开关关闭时不应调用 rerank")


@pytest.fixture
def vector_store():
    """Qdrant 实例（8 维匹配伪嵌入；目录由 conftest 隔离）。"""
    return VectorStore(dimension=8)


@pytest.fixture
async def doc_with_chunks(db_session):
    """构造一篇含两个分块的文档。"""
    doc = Document(
        id=uuid.uuid4(),
        user_id=DEFAULT_USER_ID,
        title="FastAPI 学习笔记",
        source_type="md",
        status="ready",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    rows = [
        Chunk(
            document_id=doc.id,
            chunk_index=0,
            content="FastAPI 是基于 Python 的异步 Web 框架，支持自动生成 OpenAPI 文档。",
            meta={"headings": ["简介"], "document_title": doc.title},
        ),
        Chunk(
            document_id=doc.id,
            chunk_index=1,
            content="Pydantic 负责数据校验，SQLAlchemy 负责数据库操作。",
            meta={"headings": ["技术栈"], "document_title": doc.title},
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    for r in rows:
        await db_session.refresh(r)
    return doc, rows


async def _upsert_chunks(emb, vector_store, doc, rows) -> None:
    points = [
        (
            row.id,
            (await emb.embed([row.content]))[0],
            {
                "chunk_id": str(row.id),
                "document_id": str(doc.id),
                "content": row.content,
                "meta": row.meta,
            },
        )
        for row in rows
    ]
    await vector_store.upsert(points)


# ---------- Reranker 单元测试 ----------


@pytest.mark.asyncio
async def test_rerank_sorts_desc_and_truncates() -> None:
    """按分数降序返回 (索引, 分数)，并截断到 top_n。"""
    r = FakeReranker(fixed=[0.1, 0.9, 0.5])
    ranked = await r.rerank("查询", ["甲", "乙", "丙"], top_n=2)
    assert ranked == [(1, 0.9), (2, 0.5)]


@pytest.mark.asyncio
async def test_rerank_empty_and_single_short_circuit() -> None:
    """空候选返回 []；单候选直接返回，不触发模型调用。"""
    r = FakeReranker(fixed=[0.99])
    assert await r.rerank("查询", [], top_n=3) == []
    assert await r.rerank("查询", ["唯一"], top_n=3) == [(0, 1.0)]


@pytest.mark.asyncio
async def test_rerank_all_scores_returned_when_top_n_exceeds() -> None:
    """top_n 大于候选数时全部返回。"""
    r = FakeReranker(fixed=[0.2, 0.8])
    ranked = await r.rerank("查询", ["甲", "乙"], top_n=5)
    assert ranked == [(1, 0.8), (0, 0.2)]


def test_get_reranker_singleton_lazy() -> None:
    """单例返回同一实例，且构造阶段不加载模型（懒加载）。"""
    a, b = get_reranker(), get_reranker()
    assert a is b
    assert isinstance(a, Reranker)
    assert a._model is None  # 未触发下载


# ---------- 检索链路集成测试 ----------


@pytest.mark.asyncio
async def test_hybrid_search_applies_rerank(
    db_session, vector_store, doc_with_chunks, monkeypatch
) -> None:
    """开关开启 + Fake 重排器：结果按精排分数重排、截断到前 N、分数被覆盖。"""
    monkeypatch.setattr(settings, "RAG_RERANK_ENABLED", True)
    doc, rows = doc_with_chunks
    emb = FakeEmbeddings()
    await _upsert_chunks(emb, vector_store, doc, rows)

    reranker = FakeReranker()
    results = await hybrid_search(
        db_session, "FastAPI 是什么", emb, vector_store,
        top_k=5, rerank_top_n=2, reranker=reranker,
    )

    # 期望顺序：按内容哈希分数降序取前 2
    expected = sorted(
        rows, key=lambda r: FakeCrossEncoder._score("FastAPI 是什么", r.content), reverse=True
    )[:2]
    assert [r.content for r in results] == [r.content for r in expected]
    assert len(results) == 2
    # 精排分数已覆盖（等于哈希分数），元数据保留
    for r in results:
        assert r.score == FakeCrossEncoder._score("FastAPI 是什么", r.content)
        assert r.meta["document_title"] == doc.title


@pytest.mark.asyncio
async def test_hybrid_search_rerank_disabled_keeps_rrf_behavior(
    db_session, vector_store, doc_with_chunks, monkeypatch
) -> None:
    """开关关闭：不调用 rerank，返回融合结果前 N（与旧版一致）。"""
    monkeypatch.setattr(settings, "RAG_RERANK_ENABLED", False)
    doc, rows = doc_with_chunks
    emb = FakeEmbeddings()
    await _upsert_chunks(emb, vector_store, doc, rows)

    reranker = RaisingReranker()
    results = await hybrid_search(
        db_session, "FastAPI 是什么", emb, vector_store,
        top_k=5, rerank_top_n=2, reranker=reranker,
    )
    assert reranker.calls == 0
    assert len(results) == 2
    assert len({r.chunk_id for r in results}) == len(results)  # 无重复


@pytest.mark.asyncio
async def test_rerank_candidates_single_short_circuit() -> None:
    """候选 ≤1 时原样返回，不触发精排（避免加载模型）。"""
    reranker = RaisingReranker()
    chunk = RetrievedChunk(chunk_id="c1", content="唯一候选", meta={}, score=0.5)
    out = await _rerank_candidates(reranker, "查询", [chunk], top_n=3)
    assert out == [chunk]
    assert reranker.calls == 0


@pytest.mark.asyncio
async def test_rerank_candidates_preserves_metadata_and_reorders() -> None:
    """候选 ≥2 时按精排分数重排，分数覆盖、元数据保留。"""
    reranker = FakeReranker(fixed=[0.1, 0.9])
    chunks = [
        RetrievedChunk(chunk_id="c1", content="甲", meta={"m": 1}, score=0.3),
        RetrievedChunk(chunk_id="c2", content="乙", meta={"m": 2}, score=0.7),
    ]
    out = await _rerank_candidates(reranker, "查询", chunks, top_n=2)
    assert [c.chunk_id for c in out] == ["c2", "c1"]
    assert out[0].meta == {"m": 2}
    assert out[0].score == 0.9
    assert out[1].score == 0.1
