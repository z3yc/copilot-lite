"""长期记忆管理接口：列表 / 删除。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.memory import get_memory_service
from app.models import MemoryFact, User

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
        .where(MemoryFact.user_id == user.id)
        .order_by(MemoryFact.updated_at.desc())
    )
    rows = (await db.scalars(stmt)).all()
    return [_to_out(m) for m in rows]


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除一条记忆（表 + 向量）。"""
    ok = await get_memory_service().delete(db, user.id, uuid.UUID(memory_id))
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"deleted": memory_id}
