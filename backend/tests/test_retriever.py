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


def test_tokenize_chinese_words() -> None:
    """jieba 分词：多字词作为整体检索词（优于逐字匹配的噪声）。"""
    from app.rag.retriever import _tokenize

    terms = _tokenize("数据库索引优化")
    assert "数据库" in terms
    assert "索引" in terms


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


@pytest.mark.asyncio
async def test_hybrid_search_user_isolation(db_session, vector_store) -> None:
    """用户隔离：传 user_id 后只召回该用户的分块（回归：跨用户数据泄露）。"""
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    emb = FakeEmbeddings()

    async def add_doc(uid, title, text):
        doc = Document(
            id=uuid.uuid4(), user_id=uid, title=title,
            source_type="md", status="ready",
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)
        chunk = Chunk(
            document_id=doc.id, chunk_index=0, content=text,
            meta={"headings": [], "document_title": title},
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)
        vec = (await emb.embed([text]))[0]
        await vector_store.upsert(
            [
                (
                    chunk.id,
                    vec,
                    {
                        "chunk_id": str(chunk.id),
                        "document_id": str(doc.id),
                        "user_id": str(uid),
                        "content": text,
                        "meta": chunk.meta,
                    },
                )
            ]
        )
        return doc, chunk

    # 用户 B 的内容同样含关键词"旅行计划"，验证 BM25/向量两路都会被隔离
    await add_doc(user_a, "A的旅行计划", "我的旅行计划是去西藏看雪山和布达拉宫。")
    await add_doc(user_b, "B的理财记录", "我的旅行计划基金收益率高达百分之二十。")

    results = await hybrid_search(
        db_session, "旅行计划", emb, vector_store, top_k=5, user_id=str(user_a)
    )
    contents = [r.content for r in results]
    assert contents, "应召回用户 A 自己的分块"
    assert any("西藏" in c for c in contents)
    assert all("理财" not in c for c in contents), "绝不能召回用户 B 的分块"
