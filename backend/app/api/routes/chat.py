"""聊天接口：POST /api/v1/chat。

请求：{"message": "...", "session_id": "可选，续接已有会话"}
响应：{"session_id": "...", "reply": "..."}
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import Orchestrator
from app.core.constants import DEFAULT_USER_ID
from app.core.db import get_session
from app.core.llm import get_llm
from app.models import ChatSession, Message
from app.tools import registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_session)) -> ChatResponse:
    # 1. 定位/创建会话
    if req.session_id:
        session = await db.get(ChatSession, uuid.UUID(req.session_id))
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        session = ChatSession(user_id=DEFAULT_USER_ID, title=req.message[:30])
        db.add(session)
        await db.commit()
        await db.refresh(session)

    # 2. 加载历史消息
    stmt = (
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at)
    )
    history_msgs = (await db.scalars(stmt)).all()
    history = [{"role": m.role, "content": m.content} for m in history_msgs]

    # 3. 运行 Agent 编排器
    try:
        llm = get_llm()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    orchestrator = Orchestrator(llm=llm, registry=registry)
    try:
        reply = await orchestrator.run(
            session=db, user_id=DEFAULT_USER_ID, history=history, user_message=req.message
        )
    finally:
        await llm.close()

    # 4. 持久化消息
    db.add(Message(session_id=session.id, role="user", content=req.message))
    db.add(Message(session_id=session.id, role="assistant", content=reply))
    await db.commit()

    return ChatResponse(session_id=str(session.id), reply=reply)
