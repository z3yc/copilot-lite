"""审计落点测试：统一审计表写入与字段口径（ADMIN_PLAN §3 / §9 N0.2）。"""

import uuid

import pytest
from sqlalchemy import select

from app.core.audit import record_audit
from app.models import AuditLog


@pytest.mark.asyncio
async def test_record_audit_persists_fields(db_session) -> None:
    """审计写入：字段口径正确，提交后可查（append 落库）。"""
    uid = uuid.uuid4()
    row = await record_audit(
        db_session,
        action="user.disable",
        user_id=uid,
        resource_type="user",
        resource_id=str(uid),
        result="ok",
        meta={"reason": "test"},
        request_id="req-123",
    )
    await db_session.commit()

    got = await db_session.scalar(select(AuditLog).where(AuditLog.id == row.id))
    assert got is not None
    assert got.action == "user.disable"
    assert got.user_id == uid
    assert got.resource_type == "user"
    assert got.resource_id == str(uid)
    assert got.result == "ok"
    assert got.meta == {"reason": "test"}
    assert got.request_id == "req-123"
    assert got.created_at is not None


@pytest.mark.asyncio
async def test_record_audit_defaults(db_session) -> None:
    """缺省字段：meta 为空字典、result=ok、非请求上下文不写 request_id/user_id。"""
    row = await record_audit(db_session, action="admin.login")
    await db_session.commit()

    assert row.meta == {}
    assert row.result == "ok"
    assert row.resource_type is None
    assert row.request_id is None
    assert row.user_id is None
    assert row.tenant_id is None
    assert row.workspace_id is None


@pytest.mark.asyncio
async def test_record_audit_accepts_string_user_id(db_session) -> None:
    """字符串 user_id（如路径/上下文传入）被规范化为 UUID。"""
    uid = uuid.uuid4()
    row = await record_audit(db_session, action="user.role_change", user_id=str(uid))
    await db_session.commit()
    assert row.user_id == uid
