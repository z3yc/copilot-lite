"""长期记忆管理接口：列表 / 编辑 / 删除。"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, parse_uuid
from app.core.db import get_session
from app.core.soft_delete import soft_delete
from app.memory import get_memory_service
from app.models import MemoryFact, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memories", tags=["memories"])

CATEGORY_LABEL = {
    "preference": "偏好",
    "fact": "事实",
    "background": "背景",
}


class MemoryOut(BaseModel):
    id: str
    fact: str
    category: str
    category_label: str
    confidence: float
    created_at: str | None = None


def _to_out(m: MemoryFact) -> MemoryOut:
    return MemoryOut(
        id=str(m.id),
        fact=m.fact,
        category=m.category,
        category_label=CATEGORY_LABEL.get(m.category, m.category),
        confidence=m.confidence,
        created_at=m.created_at.isoformat() if m.created_at else None,
    )


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[MemoryOut]:
    """当前用户的记忆列表（按更新时间倒序）。"""
    stmt = (
        select(MemoryFact)
        .where(MemoryFact.user_id == user.id, MemoryFact.deleted_at.is_(None))
        .order_by(MemoryFact.updated_at.desc())
    )
    rows = (await db.scalars(stmt)).all()
    return [_to_out(m) for m in rows]


class MemoryUpdate(BaseModel):
    fact: str = Field(min_length=1, max_length=300)
    category: str = Field(default="fact", pattern="^(preference|fact|background)$")


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: str,
    req: MemoryUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MemoryOut:
    """编辑记忆：修正事实内容/分类（同步更新向量）。"""
    mid = parse_uuid(memory_id)
    ok = await get_memory_service().update(db, user.id, mid, req.fact, req.category)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    row = await db.get(MemoryFact, mid)
    return _to_out(row)


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除一条记忆（软删除：标记删除 + 向量标记 deleted，可恢复）。"""
    mid = parse_uuid(memory_id)
    row = await db.get(MemoryFact, mid)
    if row is None or row.user_id != user.id or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    await soft_delete(db, row, user.id)
    try:
        await get_memory_service().vector_store.set_deleted_by_memory(str(mid), True)
    except Exception:
        logger.warning("记忆向量软删除标记失败 memory=%s", mid, exc_info=True)
    return {"deleted": memory_id, "soft": True}
