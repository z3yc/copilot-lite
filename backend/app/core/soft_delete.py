"""软删除工具：标记删除 / 恢复 / 默认过滤（AGENTS §13，强制）。

- `soft_delete()`：设置 `deleted_at` / `deleted_by`，**不物理删除**；
- `restore()`：清空标记；
- 查询层必须显式过滤 `deleted_at IS NULL`（列表/检索/统计）。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession


def mark_deleted(obj, user_id=None) -> None:
    """标记删除（不提交，供事务内批量使用）。"""
    obj.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    obj.deleted_by = uuid.UUID(str(user_id)) if user_id else None


async def soft_delete(db: AsyncSession, obj, user_id=None) -> None:
    """软删除单个对象并提交。"""
    mark_deleted(obj, user_id)
    await db.commit()


async def restore(db: AsyncSession, obj) -> None:
    """恢复软删除对象并提交。"""
    obj.deleted_at = None
    obj.deleted_by = None
    await db.commit()
