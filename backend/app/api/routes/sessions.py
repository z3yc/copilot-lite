"""会话管理接口：列表、详情（含历史消息）、创建、删除、会话附件。"""

import logging
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, parse_uuid
from app.core.db import get_session
from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    PageOut,
    normalize_page,
    page_offset,
)
from app.models import ChatSession, Message, SessionFile, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])

# 附件文本存储上限（字符），防止超大文件撑爆数据库
MAX_FILE_CHARS = 20000
# 附件原始字节上限（防超大文件读入内存导致 DoS）
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
# 单会话附件数量上限（防无限堆积）
MAX_FILES_PER_SESSION = 20

# 扩展名 → 文本提取方式
_MD_EXTS = {".md", ".markdown", ".txt"}
_CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".sql", ".html", ".htm", ".css", ".json", ".yaml", ".yml", ".toml", ".xml"}
# 会话附件允许的文件类型（后端白名单，前端 accept 只是引导）
_ALLOWED_EXTS = _MD_EXTS | _CODE_EXTS | {".pdf", ".docx"}


class SessionOut(BaseModel):
    id: str
    title: str
    message_count: int
    updated_at: str | None = None


class SessionCreate(BaseModel):
    title: str = "新会话"


class SessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=128)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str | None = None


class SessionFileOut(BaseModel):
    id: str
    filename: str
    size: int
    created_at: str | None = None


def _extract_text(filename: str, content: bytes) -> str:
    """按类型提取附件纯文本（截断存储）。"""
    ext = Path(filename).suffix.lower()
    text = ""
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        elif ext == ".docx":
            from docx import Document

            doc = Document(BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs)
        else:
            text = content.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.warning("附件文本提取失败 %s: %s", filename, exc)
        text = content.decode("utf-8", errors="replace")
    return text[:MAX_FILE_CHARS]


@router.post("", response_model=SessionOut)
async def create_session(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SessionOut:
    """创建会话（供前端上传附件等场景预创建）。"""
    session = ChatSession(user_id=user.id, title="新会话")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionOut(id=str(session.id), title=session.title, message_count=0)


@router.get("", response_model=PageOut[SessionOut])
async def list_sessions(
    q: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PageOut[SessionOut]:
    """当前用户的会话列表（按更新时间倒序，分页）；q 按标题模糊搜索。"""
    stmt = (
        select(ChatSession, func.count(Message.id).label("cnt"))
        .outerjoin(Message, Message.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    )
    if q and q.strip():
        stmt = stmt.where(ChatSession.title.ilike(f"%{q.strip()}%"))

    page, page_size = normalize_page(page, page_size)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset, limit = page_offset(page, page_size)
    rows = (await db.execute(stmt.limit(limit).offset(offset))).all()
    items = [
        SessionOut(
            id=str(s.id),
            title=s.title,
            message_count=cnt,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        )
        for s, cnt in rows
    ]
    return PageOut(items=items, total=total, page=page, page_size=page_size)


@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: str,
    req: SessionUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SessionOut:
    """重命名会话（仅限本人）。"""
    session = await _get_session(db, session_id, user)
    session.title = req.title.strip()[:128]
    await db.commit()
    await db.refresh(session)
    count = await db.scalar(
        select(func.count()).select_from(Message).where(Message.session_id == session.id)
    )
    return SessionOut(
        id=str(session.id),
        title=session.title,
        message_count=count or 0,
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
    )


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    """导出会话为 Markdown（仅限本人）。"""
    session = await _get_session(db, session_id, user)
    stmt = (
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at)
    )
    msgs = (await db.scalars(stmt)).all()
    lines = [f"# {session.title}", ""]
    for m in msgs:
        who = {"user": "用户", "assistant": "助手", "system": "系统"}.get(
            m.role, m.role
        )
        lines.append(f"## {who}\n\n{m.content}\n")
    body = "\n".join(lines)
    # Content-Disposition 文件名仅用 ASCII，避免响应头编码问题
    filename = f"session-{str(session.id)[:8]}.md"
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[MessageOut]:
    """会话的历史消息（按时间正序）。"""
    session = await _get_session(db, session_id, user)
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
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除会话（消息与附件级联删除）。"""
    session = await _get_session(db, session_id, user)
    await db.delete(session)
    await db.commit()
    return {"deleted": session_id}


# ---------------- 会话附件 ----------------

@router.post("/{session_id}/files", response_model=SessionFileOut)
async def upload_session_file(
    session_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SessionFileOut:
    """上传会话附件：提取文本入库，仅本次会话可见，不进入知识库。"""
    session = await _get_session(db, session_id, user)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 上限",
        )
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=400, detail=f"不支持的文件类型: {ext or '未知'}"
        )

    # 数量上限：防单会话附件无限堆积
    existing = await db.scalar(
        select(func.count()).select_from(SessionFile).where(SessionFile.session_id == session.id)
    )
    if (existing or 0) >= MAX_FILES_PER_SESSION:
        raise HTTPException(
            status_code=400, detail=f"附件数量已达上限（{MAX_FILES_PER_SESSION} 个）"
        )

    text = _extract_text(file.filename or "unnamed", content)
    sf = SessionFile(
        session_id=session.id,
        filename=file.filename or "unnamed",
        content=text,
        bytes_size=len(content),
    )
    db.add(sf)
    await db.commit()
    await db.refresh(sf)
    return SessionFileOut(
        id=str(sf.id),
        filename=sf.filename,
        size=sf.bytes_size or len(content),  # 真实文件字节数（语义如实）
        created_at=sf.created_at.isoformat() if sf.created_at else None,
    )


@router.get("/{session_id}/files", response_model=list[SessionFileOut])
async def list_session_files(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SessionFileOut]:
    """会话附件列表。"""
    session = await _get_session(db, session_id, user)
    stmt = (
        select(SessionFile)
        .where(SessionFile.session_id == session.id)
        .order_by(SessionFile.created_at)
    )
    files = (await db.scalars(stmt)).all()
    return [
        SessionFileOut(
            id=str(f.id),
            filename=f.filename,
            size=f.bytes_size or 0,
            created_at=f.created_at.isoformat() if f.created_at else None,
        )
        for f in files
    ]


@router.delete("/{session_id}/files/{file_id}")
async def delete_session_file(
    session_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除会话附件。"""
    session = await _get_session(db, session_id, user)
    sf = await db.get(SessionFile, parse_uuid(file_id))
    if sf is None or sf.session_id != session.id:
        # 附件必须属于该会话（对象级授权落在被操作对象上）
        raise HTTPException(status_code=404, detail="附件不存在")
    await db.delete(sf)
    await db.commit()
    return {"deleted": file_id}


async def _get_session(db: AsyncSession, session_id: str, user: User) -> ChatSession:
    """定位会话并校验归属（越权访问返回 404）。"""
    session = await db.get(ChatSession, parse_uuid(session_id))
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session
