"""用户软删除 / 状态 / 部分唯一索引口径测试（ADMIN_PLAN §9 N0.6）。

覆盖：默认 status=active、活跃用户用户名唯一、软删后用户名可重用。
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import User


@pytest.mark.asyncio
async def test_user_default_status_active(db_session) -> None:
    """新用户默认 status=active，软删除字段为空。"""
    user = User(username="alice", password_hash="x")
    db_session.add(user)
    await db_session.commit()

    assert user.status == "active"
    assert user.deleted_at is None
    assert user.delete_reason is None


@pytest.mark.asyncio
async def test_active_username_unique(db_session) -> None:
    """两个活跃用户不能同名（部分唯一索引仍然生效）。"""
    db_session.add(User(username="alice", password_hash="x"))
    await db_session.commit()

    db_session.add(User(username="alice", password_hash="x"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_username_reusable_after_soft_delete(db_session) -> None:
    """软删用户后，同名用户名可再次注册（部分唯一索引 WHERE deleted_at IS NULL）。"""
    first = User(username="bob", password_hash="x")
    db_session.add(first)
    await db_session.commit()

    first.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    first.deleted_by = first.id
    first.delete_reason = "用户注销"
    await db_session.commit()

    # 同名重建不应冲突
    db_session.add(User(username="bob", password_hash="y"))
    await db_session.commit()
