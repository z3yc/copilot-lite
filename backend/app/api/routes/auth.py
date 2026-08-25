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
