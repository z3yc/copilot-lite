"""会话管理接口：列表、详情（含历史消息）、删除。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_USER_ID
from app.core.db import get_session
from app.models import ChatSession, Message

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    id: str
    title: str
    message_count: int
    updated_at: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str | None = None


@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_session)) -> list[SessionOut]:
    """当前用户的会话列表（按更新时间倒序）。"""
    stmt = (
        select(ChatSession, func.count(Message.id).label("cnt"))
        .outerjoin(Message, Message.session_id == ChatSession.id)
        .where(ChatSession.user_id == DEFAULT_USER_ID)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        SessionOut(
            id=str(s.id),
            title=s.title,
            message_count=cnt,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        )
        for s, cnt in rows
    ]


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def session_messages(session_id: str, db: AsyncSession = Depends(get_session)) -> list[MessageOut]:
    """会话的历史消息（按时间正序）。"""
    session = await db.get(ChatSession, uuid.UUID(session_id))
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    stmt = (
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at)
    )
    msgs = (await db.scalars(stmt)).all()
    return [
        MessageOut(
            id=str(m.id),
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in msgs
    ]


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_session)) -> dict:
    """删除会话（消息级联删除）。"""
    session = await db.get(ChatSession, uuid.UUID(session_id))
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    await db.delete(session)
    await db.commit()
    return {"deleted": session_id}
