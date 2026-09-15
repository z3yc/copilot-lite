"""回收站接口：列出软删除数据并恢复（AGENTS §13/§14）。

- GET  /trash                       当前用户已软删除的数据（跨类型）
- POST /trash/{item_type}/{item_id}/restore   恢复
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.memory import get_memory_service
from app.models import ChatSession, Chunk, Document, MemoryFact, Todo, User, WikiPage, WikiSpace
from app.rag import get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trash", tags=["trash"])

# 支持回收站的类型 → (模型, 展示字段)
_TYPES = {
    "todo": (Todo, "title"),
    "document": (Document, "title"),
    "session": (ChatSession, "title"),
    "memory": (MemoryFact, "fact"),
    "wiki_page": (WikiPage, "title"),
}


class TrashItem(BaseModel):
    type: str
    id: str
    label: str
    deleted_at: datetime | None = None


@router.get("", response_model=list[TrashItem])
async def list_trash(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[TrashItem]:
    """列出当前用户所有已软删除的数据（按删除时间倒序）。"""
    items: list[TrashItem] = []
    for type_name, (model, label_field) in _TYPES.items():
        rows = (
            await db.scalars(
                select(model).where(
                    model.user_id == user.id, model.deleted_at.is_not(None)
                )
            )
        ).all()
        items.extend(
            TrashItem(
                type=type_name,
                id=str(row.id),
                label=str(getattr(row, label_field) or "")[:120],
                deleted_at=row.deleted_at,
            )
            for row in rows
        )
    items.sort(key=lambda i: i.deleted_at.timestamp() if i.deleted_at else 0, reverse=True)
    return items


async def _restore_document(db: AsyncSession, doc: Document) -> None:
    await db.execute(
        update(Chunk)
        .where(Chunk.document_id == doc.id, Chunk.deleted_at.is_not(None))
        .values(deleted_at=None, deleted_by=None)
    )
    try:
        await get_vector_store().set_deleted_by_document(doc.id, False)
    except Exception:
        logger.warning("文档向量恢复标记失败 document=%s", doc.id, exc_info=True)


@router.post("/{item_type}/{item_id}/restore")
async def restore_item(
    item_type: str,
    item_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """恢复一条已软删除数据（含派生索引标记）。"""
    entry = _TYPES.get(item_type)
    if entry is None:
        raise HTTPException(status_code=400, detail=f"不支持的回收类型: {item_type}")
    model, _ = entry
    try:
        uid = uuid.UUID(item_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="数据不存在") from None

    row = await db.get(model, uid)
    if row is None or row.user_id != user.id or row.deleted_at is None:
        raise HTTPException(status_code=404, detail="数据不存在")

    row.deleted_at = None
    row.deleted_by = None
    if item_type == "document":
        await _restore_document(db, row)
    elif item_type == "wiki_page" and row.document_id:
        doc = await db.get(Document, row.document_id)
        if doc is not None:
            await _restore_document(db, doc)
            doc.deleted_at = None
            doc.deleted_by = None
        # 恢复页面时同步恢复其所属空间（否则空间仍隐藏页面）
        space = await db.get(WikiSpace, row.space_id)
        if space is not None:
            space.deleted_at = None
            space.deleted_by = None
    elif item_type == "memory":
        try:
            await get_memory_service().vector_store.set_deleted_by_memory(
                str(row.id), False
            )
        except Exception:
            logger.warning("记忆向量恢复标记失败 memory=%s", row.id, exc_info=True)
    await db.commit()
    return {"restored": item_id, "type": item_type}
