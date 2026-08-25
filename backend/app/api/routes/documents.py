"""文档管理接口：上传/摄取、列表、详情、删除。"""

import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_USER_ID
from app.core.db import get_session
from app.models import Chunk, Document
from app.rag import (
    IngestError,
    get_embedding_service,
    get_vector_store,
    ingest_document,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

# 扩展名 → source_type 映射
_EXT_MAP = {
    ".md": "md",
    ".markdown": "md",
    ".txt": "md",
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".tsx": "code",
    ".jsx": "code",
    ".java": "code",
    ".go": "code",
    ".rs": "code",
    ".c": "code",
    ".cpp": "code",
    ".sql": "code",
    ".html": "web",
    ".htm": "web",
}
_DATA_DIR = Path("./data")


def _detect_source_type(filename: str) -> str:
    return _EXT_MAP.get(Path(filename).suffix.lower(), "md")


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    status: str
    chunk_count: int = 0
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
) -> DocumentOut:
    """上传文档并触发摄取（解析→分块→嵌入→入库）。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    source_type = _detect_source_type(file.filename or "")
    document = Document(
        user_id=DEFAULT_USER_ID,
        title=file.filename or "未命名文档",
        source_type=source_type,
        status="uploaded",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # 保存原件副本
    try:
        save_dir = _DATA_DIR / str(document.id)
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / (file.filename or "unnamed")).write_bytes(content)
    except OSError as exc:
        logger.warning("原件保存失败（不影响摄取）: %s", exc)

    # 同步摄取（个人量级够用；大数据量可改后台任务）
    try:
        document.status = "parsing"
        await db.commit()
        await ingest_document(
            db, document, content, get_embedding_service(), get_vector_store()
        )
        document.status = "ready"
    except (IngestError, Exception) as exc:
        document.status = "failed"
        document.extra = {"error": str(exc)}
        logger.exception("文档摄取失败: %s", file.filename)
        raise HTTPException(status_code=422, detail=f"文档摄取失败: {exc}") from exc
    finally:
        await db.commit()

    return await _to_out(db, document)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    q: str | None = None,
    type: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[DocumentOut]:
    """文档列表。

    q:    内容级搜索关键词（标题或分块内容包含）
    type: 按来源类型过滤（md / pdf / docx / code / web）
    """
    stmt = select(Document)
    if q and q.strip():
        from sqlalchemy import or_

        kw = f"%{q.strip()}%"
        content_hits = select(Chunk.document_id).where(Chunk.content.ilike(kw))
        stmt = stmt.where(
            or_(Document.title.ilike(kw), Document.id.in_(content_hits))
        )
    if type:
        stmt = stmt.where(Document.source_type == type)
    stmt = stmt.order_by(Document.created_at.desc())
    docs = (await db.scalars(stmt)).all()
    return [await _to_out(db, d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_session)) -> DocumentOut:
    doc = await _get_doc(db, doc_id)
    return await _to_out(db, doc)


class ChunkOut(BaseModel):
    chunk_index: int
    content: str
    headings: list[str] = []
    page: int | None = None


class DocumentDetail(DocumentOut):
    error: str | None = None
    chunks: list[ChunkOut] = []


@router.get("/{doc_id}/chunks", response_model=DocumentDetail)
async def get_document_detail(
    doc_id: str, db: AsyncSession = Depends(get_session)
) -> DocumentDetail:
    """文档详情：基础信息 + 摄取失败原因 + 分块列表（含标题路径/页码）。"""
    doc = await _get_doc(db, doc_id)
    stmt = select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)
    chunks = (await db.scalars(stmt)).all()

    detail = DocumentDetail.model_validate(doc)
    detail.chunk_count = len(chunks)
    detail.error = (doc.extra or {}).get("error")
    detail.chunks = [
        ChunkOut(
            chunk_index=c.chunk_index,
            content=c.content,
            headings=c.meta.get("headings", []) if c.meta else [],
            page=c.meta.get("page") if c.meta else None,
        )
        for c in chunks
    ]
    return detail


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_session)) -> dict:
    """删除文档（PostgreSQL 分块 + Qdrant 向量 + 原件）。"""
    doc = await _get_doc(db, doc_id)
    # 1. 删除 Qdrant 向量
    await get_vector_store().delete_by_document(doc.id)
    # 2. 删除分块与文档（级联）
    await db.delete(doc)
    await db.commit()
    # 3. 删除原件目录
    try:
        import shutil

        shutil.rmtree(_DATA_DIR / str(doc.id), ignore_errors=True)
    except OSError:
        pass
    return {"deleted": doc_id}


async def _get_doc(db: AsyncSession, doc_id: str) -> Document:
    doc = await db.get(Document, uuid.UUID(doc_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


async def _to_out(db: AsyncSession, doc: Document) -> DocumentOut:
    count = await db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    out = DocumentOut.model_validate(doc)
    out.chunk_count = count or 0
    return out
