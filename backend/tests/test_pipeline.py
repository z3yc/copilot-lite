"""摄取流水线测试：FakeEmbeddings + 临时 Qdrant，不下载模型。"""

import hashlib

import pytest

from app.core.constants import DEFAULT_USER_ID
from app.models import Chunk, Document
from app.rag.pipeline import IngestError, ingest_document
from app.rag.vector_store import VectorStore


class FakeEmbeddings:
    """确定性伪嵌入（8 维）。"""

    dim = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
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
async def test_ingest_markdown(db_session, vector_store) -> None:
    """Markdown 完整摄取：解析→分块→chunks→嵌入→Qdrant。"""
    content = """# 第一章

第一章内容。

## 第一节

包含检索关键词的内容。
""".encode()

    doc = Document(user_id=DEFAULT_USER_ID, title="测试笔记.md", source_type="md")
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    count = await ingest_document(db_session, doc, content, FakeEmbeddings(), vector_store)
    assert count == 2  # 两个章节 = 两个分块

    # chunks 表已写入
    from sqlalchemy import select

    rows = (await db_session.scalars(select(Chunk))).all()
    assert len(rows) == 2
    assert rows[0].vector_id is not None

    # Qdrant 已有向量
    total = vector_store._client.count(vector_store.collection).count
    assert total == 2


@pytest.mark.asyncio
async def test_ingest_unsupported_type(db_session, vector_store) -> None:
    """不支持的文档类型抛 IngestError。"""
    doc = Document(user_id=DEFAULT_USER_ID, title="x.xyz", source_type="xyz")
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    with pytest.raises(IngestError):
        await ingest_document(db_session, doc, b"content", FakeEmbeddings(), vector_store)
