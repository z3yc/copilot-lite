"""查询改写与多查询召回测试（Fake LLM / Fake 嵌入，不触网不下载模型）。"""

import hashlib
import uuid

import pytest

from app.core.constants import DEFAULT_USER_ID
from app.core.llm import ChatResult
from app.models import Chunk, Document
from app.rag.query_rewriter import QueryRewriter
from app.rag.retriever import multi_query_search
from app.rag.vector_store import VectorStore
from app.tools import registry
from app.tools.base import ToolContext


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def chat(self, messages, tools=None, temperature=0.7):
        return ChatResult(content=self.content)

    async def close(self) -> None:
        pass


class _FakeEmbeddings:
    dim = 8

    async def embed(self, texts):
        out = []
        for t in texts:
            h = hashlib.md5(t.encode()).hexdigest()
            out.append([float(int(h[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)])
        return out


@pytest.fixture
def vector_store():
    """Qdrant 实例（8 维；目录由 conftest 隔离）。"""
    return VectorStore(dimension=8)


@pytest.mark.asyncio
async def test_rewriter_returns_variants() -> None:
    """LLM 输出改写列表：返回 [原问题, 改写...]，去重且不超过上限。"""
    rewriter = QueryRewriter(
        llm=_FakeLLM('["FastAPI 如何做依赖注入", "FastAPI 怎么用"]')
    )
    variants = await rewriter.rewrite("FastAPI 的依赖注入怎么用")
    assert variants[0] == "FastAPI 的依赖注入怎么用"
    assert "FastAPI 如何做依赖注入" in variants
    assert len(variants) == 3  # 原问题 + 2 个改写（默认上限）


@pytest.mark.asyncio
async def test_rewriter_fallback_on_bad_llm() -> None:
    """LLM 输出非法 / 调用异常：回退 [原问题]，不阻塞检索。"""
    assert await QueryRewriter(llm=_FakeLLM("不是JSON")).rewrite("问题") == ["问题"]

    class Boom:
        async def chat(self, messages, tools=None, temperature=0.7):
            raise RuntimeError("boom")

        async def close(self) -> None:
            pass

    assert await QueryRewriter(llm=Boom()).rewrite("问题") == ["问题"]


@pytest.mark.asyncio
async def test_multi_query_search_fuses_results(db_session, vector_store) -> None:
    """多查询召回：不同改写命中的不同文档都被融合进最终结果。"""
    emb = _FakeEmbeddings()
    user_id = DEFAULT_USER_ID

    async def add_doc(title: str, content: str) -> Chunk:
        doc = Document(user_id=user_id, title=title, source_type="md", status="ready")
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)
        chunk = Chunk(
            document_id=doc.id,
            chunk_index=0,
            content=content,
            meta={"headings": [], "document_title": title},
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)
        vec = (await emb.embed([content]))[0]
        await vector_store.upsert(
            [
                (
                    chunk.id,
                    vec,
                    {
                        "chunk_id": str(chunk.id),
                        "document_id": str(doc.id),
                        "user_id": str(user_id),
                        "content": content,
                        "meta": chunk.meta,
                    },
                )
            ]
        )
        return chunk

    await add_doc("A", "FastAPI 的依赖注入使用 Depends 实现。")
    await add_doc("B", "数据库索引失效时查看执行计划。")

    results = await multi_query_search(
        db_session,
        ["FastAPI 依赖注入", "数据库索引失效"],
        emb,
        vector_store,
        top_k=3,
        rerank_top_n=5,
        user_id=str(user_id),
    )
    contents = [r.content for r in results]
    assert any("依赖注入" in c for c in contents)
    assert any("执行计划" in c for c in contents)


@pytest.mark.asyncio
async def test_kb_search_uses_rewrite_when_enabled(db_session, monkeypatch) -> None:
    """开关开启时 kb_search 走改写→多查询召回链路。"""
    import app.tools.kb_tool as kb_module
    from app.core.config import settings

    captured: dict = {}

    class FakeRewriter:
        async def rewrite(self, query):
            captured["query"] = query
            return [query, "改写1"]

    async def fake_multi(db, queries, embeddings, vector_store, top_k, user_id, **kw):
        captured["queries"] = queries
        return []

    monkeypatch.setattr(kb_module, "get_rewriter", lambda: FakeRewriter())
    monkeypatch.setattr(kb_module, "multi_query_search", fake_multi)
    monkeypatch.setattr(settings, "RAG_QUERY_REWRITE_ENABLED", True)

    ctx = ToolContext(session=db_session, user_id=uuid.uuid4())
    await registry.execute("kb_search", '{"query": "测试"}', ctx)
    assert captured["queries"] == ["测试", "改写1"]
