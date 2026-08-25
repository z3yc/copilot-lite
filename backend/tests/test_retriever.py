"""混合检索测试：使用伪嵌入（不下载模型）与临时 Qdrant。"""

import hashlib
import uuid

import pytest

from app.core.constants import DEFAULT_USER_ID
from app.models import Chunk, Document
from app.rag.retriever import hybrid_search
from app.rag.vector_store import VectorStore

_TEST_QDRANT = "test_qdrant_data"


class FakeEmbeddings:
    """基于文本哈希的确定性伪嵌入（维度 8）。"""

    dim = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = hashlib.md5(t.encode()).hexdigest()
            out.append([float(int(h[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)])
        return out


@pytest.fixture
async def vector_store(tmp_path, monkeypatch):
    """临时 Qdrant 本地实例（8 维以匹配伪嵌入）。"""
    monkeypatch.setattr("app.rag.vector_store.settings.QDRANT_PATH", str(tmp_path / "qdrant"))
    vs = VectorStore(dimension=8)
    yield vs
    # Qdrant 本地模式的文件句柄由 GC 管理，无需显式清理


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


@pytest.mark.asyncio
async def test_hybrid_search_returns_results(db_session, vector_store, doc_with_chunks) -> None:
    """向量 + BM25 混合检索能召回相关分块。"""
    doc, rows = doc_with_chunks
    emb = FakeEmbeddings()

    # 写入向量
    points = []
    for row in rows:
        vec = (await emb.embed([row.content]))[0]
        points.append(
            (
                row.id,
                vec,
                {
                    "chunk_id": str(row.id),
                    "document_id": str(doc.id),
                    "content": row.content,
                    "meta": row.meta,
                },
            )
        )
    await vector_store.upsert(points)

    # 关键词命中（BM25 路径）：查询包含"FastAPI"
    results = await hybrid_search(db_session, "FastAPI 是什么", emb, vector_store, top_k=5)
    assert results, "应至少召回一条结果"
    assert "FastAPI" in results[0].content
    assert results[0].meta["headings"] == ["简介"]


@pytest.mark.asyncio
async def test_hybrid_search_rrf_fusion(db_session, vector_store, doc_with_chunks) -> None:
    """RRF 融合：两路检索结果合并去重。"""
    doc, rows = doc_with_chunks
    emb = FakeEmbeddings()
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

    results = await hybrid_search(db_session, "数据库 校验 操作", emb, vector_store, top_k=5)
    # 不抛错且结果唯一（按 chunk_id 去重）
    ids = [r.chunk_id for r in results]
    assert len(ids) == len(set(ids))
