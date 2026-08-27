"""聊天接口：非流式 + SSE 流式。

- POST /api/v1/chat            普通响应 {"session_id", "reply"}
- POST /api/v1/chat/stream     SSE 流式（打字机效果）

SSE 事件序列：
    event: session  data: {"session_id": "..."}
    event: chunk    data: {"text": "..."}    （回复内容分片）
    event: done     data: {}
"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import Orchestrator
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_session
from app.core.llm import get_llm
from app.memory import get_memory_service
from app.models import ChatSession, Message, User
from app.tools import registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# SSE 心跳间隔（秒）：长工具轮期间无文本输出，靠注释帧保活连接
_HEARTBEAT_SECONDS = 15.0


async def _resolve_session(
    db: AsyncSession, session_id: str | None, title: str, user: User
) -> ChatSession:
    """定位（校验归属）或创建会话。"""
    if session_id:
        session = await db.get(ChatSession, uuid.UUID(session_id))
        if session is None or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="会话不存在")
        return session
    session = ChatSession(user_id=user.id, title=title[:30])
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def _load_history(db: AsyncSession, session_id) -> list[dict]:
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    msgs = (await db.scalars(stmt)).all()
    return [{"role": m.role, "content": m.content} for m in msgs]


# 每个附件注入上下文的文本上限
_MAX_FILE_CONTEXT = 1500
# 最多注入的附件数
_MAX_FILES = 5


async def _load_session_file_context(db: AsyncSession, session_id) -> list[dict] | None:
    """加载会话附件，作为 system 上下文注入（仅本次会话，不进知识库）。"""
    from app.models import SessionFile

    stmt = (
        select(SessionFile)
        .where(SessionFile.session_id == session_id)
        .order_by(SessionFile.created_at)
    )
    files = (await db.scalars(stmt)).all()
    if not files:
        return None
    parts = [
        f"【{f.filename}】\n{f.content[:_MAX_FILE_CONTEXT]}"
        for f in files[:_MAX_FILES]
    ]
    return [
        {
            "role": "system",
            "content": (
                "本次会话中用户上传了以下文件，回答相关问题时请优先基于这些内容，"
                "并注明来自哪个文件：\n" + "\n\n".join(parts)
            ),
        }
    ]


async def _build_context(
    db: AsyncSession, session_id, history: list[dict], user_message: str, user_id
) -> list[dict]:
    """组装上下文：会话附件（system）+ 长期记忆（system）+ 历史消息。

    记忆召回按当前问题执行（向量检索，无 LLM 成本），
    等价于"会话开始注入 + 话题切换自动补充"的混合策略。
    """
    parts: list[dict] = []
    file_ctx = await _load_session_file_context(db, session_id)
    if file_ctx:
        parts.extend(file_ctx)
    memories = await get_memory_service().recall(db, user_id, user_message)
    if memories:
        parts.append(
            {
                "role": "system",
                "content": "关于用户的长期记忆（回答时自然参考，但不要提及\"记忆\"一词）：\n"
                + "\n".join(f"- {m}" for m in memories),
            }
        )
    return parts + history


def _build_agent():
    """按配置选择对话引擎：langgraph（多 Agent，默认）/ handwritten（手写 ReAct）。

    LangGraph 引擎内部创建 langchain ChatOpenAI（DeepSeek 兼容 OpenAI 接口）；
    手写引擎复用 LLMClient（get_llm 入口）。两者运行协议一致：run / run_stream / close。
    """
    if settings.AGENT_ENGINE == "langgraph":
        from app.agent.langgraph_engine import LangGraphEngine

        return LangGraphEngine(registry=registry)
    return Orchestrator(llm=get_llm(), registry=registry)


async def _run_agent(db: AsyncSession, history: list[dict], message: str, user_id) -> str:
    try:
        agent = _build_agent()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return await agent.run(
            session=db, user_id=user_id, history=history, user_message=message
        )
    finally:
        await agent.close()


async def _run_agent_stream(db: AsyncSession, history: list[dict], message: str, user_id):
    """按配置选择引擎并流式运行，逐文本增量产出（供 SSE chunk 事件）。"""
    try:
        agent = _build_agent()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        async for text in agent.run_stream(
            session=db, user_id=user_id, history=history, user_message=message
        ):
            yield text
    finally:
        await agent.close()


async def _persist(db: AsyncSession, session_id, user_msg: str, reply: str) -> None:
    db.add(Message(session_id=session_id, role="user", content=user_msg))
    db.add(Message(session_id=session_id, role="assistant", content=reply))
    await db.commit()


async def _persist_partial(db: AsyncSession, session_id, reply_parts: list[str]) -> None:
    """异常中断时尽力保存已生成的部分回复（防流式中断丢消息）。"""
    if not reply_parts:
        return
    try:
        db.add(
            Message(session_id=session_id, role="assistant", content="".join(reply_parts))
        )
        await db.commit()
    except Exception:  # noqa: BLE001  部分落库失败不应掩盖原始异常
        logger.warning("部分回复落库失败", exc_info=True)


async def _background_extract_memories(session_id, user_id) -> None:
    """会话结束后台提取记忆（独立会话，不阻塞响应）。"""
    try:
        from app.core.db import async_session_factory

        async with async_session_factory() as db:
            history = await _load_history(db, session_id)
            msgs = [{"role": m["role"], "content": m["content"]} for m in history]
            await get_memory_service().extract_from_session(db, user_id, session_id, msgs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("后台记忆提取失败: %s", exc)


def _schedule_memory_extract(session_id, user_id) -> None:
    """异步调度记忆提取（不阻塞响应返回；测试环境关闭）。"""
    if not settings.MEMORY_EXTRACT_ENABLED:
        return
    import asyncio

    asyncio.create_task(_background_extract_memories(session_id, user_id))


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ChatResponse:
    """非流式对话。"""
    session = await _resolve_session(db, req.session_id, req.message, user)
    history = await _build_context(
        db, session.id, await _load_history(db, session.id), req.message, user.id
    )
    reply = await _run_agent(db, history, req.message, user.id)
    await _persist(db, session.id, req.message, reply)
    _schedule_memory_extract(session.id, user.id)
    return ChatResponse(session_id=str(session.id), reply=reply)


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """SSE 流式对话（token 级流式，打字机效果）。

    引擎按配置选择（LangGraph 多 Agent 默认 / 手写 ReAct）：
    模型文本轮逐 token 实时转发（chunk 事件），工具调用轮在后台执行
    （不阻塞、不产生用户可见文本）。
    """
    session = await _resolve_session(db, req.session_id, req.message, user)
    history = await _build_context(
        db, session.id, await _load_history(db, session.id), req.message, user.id
    )

    # 引擎/Key 检查提前到响应前（错误可返回 HTTP 状态码）
    try:
        _build_agent()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def event_gen() -> AsyncIterator[str]:
        # 1. 先发会话事件
        yield _sse("session", {"session_id": str(session.id)})

        # 2. 先持久化用户消息（客户端中途断开也不丢用户输入）
        db.add(Message(session_id=session.id, role="user", content=req.message))
        await db.commit()

        # 3. token 级流式运行引擎（逐 chunk 转发；长等待期间发心跳保活）
        reply_parts: list[str] = []
        agent_stream = _run_agent_stream(db, history, req.message, user.id)
        try:
            while True:
                try:
                    text = await asyncio.wait_for(
                        anext(agent_stream), timeout=_HEARTBEAT_SECONDS
                    )
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                reply_parts.append(text)
                yield _sse("chunk", {"text": text})
        except HTTPException as exc:
            await _persist_partial(db, session.id, reply_parts)
            yield _sse("error", {"detail": exc.detail})
            return
        except Exception:  # noqa: BLE001  通用异常也必须显式终止，不能裸断 SSE
            logger.exception("流式对话生成异常")
            await _persist_partial(db, session.id, reply_parts)
            yield _sse("error", {"detail": "生成中断，请重试"})
            return

        # 4. 落库成功后才发 done（done 语义 = 已持久化）
        reply = "".join(reply_parts)
        db.add(Message(session_id=session.id, role="assistant", content=reply))
        await db.commit()
        yield _sse("done", {})
        _schedule_memory_extract(session.id, user.id)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
