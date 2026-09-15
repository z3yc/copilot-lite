"""统一审计写入口（append-only，ADMIN_PLAN §9 N0.2 / AGENTS §15）。

设计：
- **与业务同事务**：只 ``add`` + ``flush``，不 ``commit``，提交时机交由调用方，
  保证"写操作 + 审计"原子落库；
- ``request_id`` / ``user_id`` 缺省时从请求上下文（contextvars）自动补全；
- 只写不删改（append-only），审计即溯源依据。
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_request_id, get_user_id
from app.models.audit_log import AuditLog

# 审计结果口径
RESULT_OK = "ok"  # 操作成功
RESULT_DENIED = "denied"  # 越权 / 被护栏拒绝
RESULT_ERROR = "error"  # 执行失败


def _coerce_uuid(value: object | None) -> uuid.UUID | None:
    """把 UUID / uuid 字符串规范化为 UUID；无效值返回 None。"""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    user_id: object | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    result: str = RESULT_OK,
    meta: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """追加一条审计日志（flush，不提交；参与调用方事务）。

    ``user_id`` 与 ``request_id`` 未显式传入时，从请求上下文补全；
    非请求上下文（后台任务 / 测试）下为 None。
    """
    rid = request_id or get_request_id()
    if rid == "-":
        rid = None
    row = AuditLog(
        action=action,
        user_id=_coerce_uuid(user_id) if user_id is not None else _coerce_uuid(get_user_id()),
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        meta=meta or {},
        request_id=rid,
    )
    db.add(row)
    await db.flush()
    return row
