"""认证接口：注册 / 登录 / 当前用户。

- POST /api/v1/auth/register  注册（返回 token）
- POST /api/v1/auth/login     登录（返回 token）
- GET  /api/v1/auth/me        当前用户信息（需认证）
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.core.security import create_token, hash_password, verify_password
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class UserOut(BaseModel):
    id: str
    username: str
    role: str


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        token=create_token(user.id),
        user={"id": str(user.id), "username": user.username, "role": user.role},
    )


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_session)) -> AuthResponse:
    """注册新用户并返回令牌。"""
    exists = await db.scalar(select(User).where(User.username == req.username))
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 为新用户创建默认分类（工作/生活/学习/其他）
    from app.models import Category
    from app.models.category import DEFAULT_CATEGORIES

    for c in DEFAULT_CATEGORIES:
        db.add(Category(user_id=user.id, **c))
    await db.commit()

    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_session)) -> AuthResponse:
    """登录并返回令牌。"""
    user = await db.scalar(select(User).where(User.username == req.username))
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    """当前登录用户信息。"""
    return UserOut(id=str(user.id), username=user.username, role=user.role)


class ProfileOut(UserOut):
    created_at: str | None = None
    session_count: int = 0
    message_count: int = 0
    todo_count: int = 0
    doc_count: int = 0
    chunk_count: int = 0


@router.get("/profile", response_model=ProfileOut)
async def profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ProfileOut:
    """个人主页数据：账号信息 + 使用统计。"""
    from sqlalchemy import func

    from app.models import ChatSession, Chunk, Document, Message, Todo

    session_count = await db.scalar(
        select(func.count()).select_from(ChatSession).where(ChatSession.user_id == user.id)
    )
    todo_count = await db.scalar(
        select(func.count()).select_from(Todo).where(Todo.user_id == user.id)
    )
    doc_count = await db.scalar(
        select(func.count()).select_from(Document).where(Document.user_id == user.id)
    )
    chunk_count = await db.scalar(
        select(func.count())
        .select_from(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.user_id == user.id)
    )
    message_count = await db.scalar(
        select(func.count())
        .select_from(Message)
        .join(ChatSession, Message.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id)
    )

    return ProfileOut(
        id=str(user.id),
        username=user.username,
        role=user.role,
        created_at=user.created_at.isoformat() if user.created_at else None,
        session_count=session_count or 0,
        message_count=message_count or 0,
        todo_count=todo_count or 0,
        doc_count=doc_count or 0,
        chunk_count=chunk_count or 0,
    )


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=64)


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """修改密码（需验证原密码）。"""
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return {"ok": True, "message": "密码已更新"}
