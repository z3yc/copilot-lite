"""摄取流水线：把原始文档转化为可检索的分块向量。

流程：解析 → 分块 → 写入 chunks 表 → 嵌入 → 写入 Qdrant → 更新文档状态。
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document
from app.rag.chunking import chunk_document
from app.rag.embeddings import EmbeddingService
from app.rag.parsers import get_parser
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestError(Exception):
    """摄取失败（解析器缺失/内容为空等）。"""


async def ingest_document(
    db: AsyncSession,
    document: Document,
    content: bytes,
    embeddings: EmbeddingService,
    vector_store: VectorStore,
) -> int:
    """执行一次完整摄取，返回生成的分块数量。

    任一步骤失败会抛 IngestError，由调用方将文档状态置为 failed。
    """
    parser = get_parser(document.source_type)
    if parser is None:
        raise IngestError(f"不支持的文档类型: {document.source_type}")

    # 1. 解析
    parsed = parser.parse(content, meta={"title": document.title})

    # 2. 分块
    chunks = chunk_document(parsed)
    if not chunks:
        raise IngestError("文档解析后无有效内容")

    # 3. 写入 chunks 表
    chunk_rows: list[Chunk] = []
    for i, c in enumerate(chunks):
        chunk_rows.append(
            Chunk(
                document_id=document.id,
                chunk_index=i,
                content=c.content,
                meta={**c.meta, "document_title": document.title},
            )
        )
    db.add_all(chunk_rows)
    await db.commit()
    for row in chunk_rows:
        await db.refresh(row)

    # 4. 嵌入（全量批量）
    texts = [c.content for c in chunks]
    vectors = await embeddings.embed(texts)

    # 5. 写入 Qdrant（payload 携带引用元数据）
    points = [
        (
            row.id,
            vector,
            {
                "chunk_id": str(row.id),
                "document_id": str(document.id),
                "user_id": str(document.user_id),
                "content": row.content,
                "meta": row.meta,
            },
        )
        for row, vector in zip(chunk_rows, vectors, strict=True)
    ]
    await vector_store.upsert(points)

    # 6. 回写 vector_id（可追溯）
    for row, _ in zip(chunk_rows, vectors, strict=True):
        row.vector_id = str(row.id)
    await db.commit()

    logger.info("文档 %s 摄取完成: %d 个分块", document.title, len(chunks))
    return len(chunks)
