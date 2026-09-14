"""认证依赖：从 Authorization header 解析 JWT → 返回当前用户。"""

import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import set_user_id
from app.core.db import get_session
from app.core.security import decode_token
from app.models import User

# 可选认证：未携带 token 时不报错（供公开接口用）
bearer_scheme = HTTPBearer(auto_error=False)


def parse_uuid(value: str) -> uuid.UUID:
    """路径参数 UUID 解析；畸形输入返回 404（而非 500 堆栈）。"""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="资源不存在") from None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    """从 Bearer token 解析当前用户；无效/缺失/版本不匹配抛 401。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        user_id, token_version = decode_token(credentials.credentials)
        uid = uuid.UUID(user_id)
    except Exception:  # noqa: BLE001  JWT 解码失败统一视为未认证
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录") from None

    user = await db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    # token 版本校验：改密/封号后旧 token 立即失效（无状态撤销）
    if user.token_version != token_version:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    set_user_id(user.id)  # 写入请求上下文，WARN/ERROR 日志自动携带 user_id
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """管理员依赖：非 admin 一律 403，不泄露资源存在性。

    当前按 ``User.role == "admin"`` 判定；日后接入 RBAC 时，仅需把本依赖
    替换为 ``require_permission("admin.read")``，路由与业务无需改动（ADMIN_PLAN §7）。
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="无权限")
    if not settings.ADMIN_ENABLED:
        # 功能整体关闭：对管理员也返回 404（不泄露后台存在性）
        raise HTTPException(status_code=404, detail="资源不存在")
    return user
