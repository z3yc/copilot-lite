"""用户模型。

软删除（AGENTS §13 / ADMIN_PLAN §9 N0.6）：
- `deleted_at` / `deleted_by` / `delete_reason`：注销/删号只标记不物理删除；
- `status`：active / disabled（禁用与软删除语义不同，禁用可恢复登录）；
- `username` 唯一约束改为**部分唯一索引**（`WHERE deleted_at IS NULL`），
  允许删号后重用同一用户名。
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, SoftDeleteMixin

# 账号状态
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"


class User(SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # 部分唯一索引：仅活跃（未软删）用户间用户名唯一，删号后可重用
        Index(
            "uq_users_username_active",
            "username",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32), default="user")  # user / admin
    # 账号状态：active（正常）/ disabled（禁用，可恢复）
    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_ACTIVE, server_default=STATUS_ACTIVE
    )
    # 软删除原因（可空；删号二次确认时可填）
    delete_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # JWT 版本号：改密/封号时 +1，旧 token 全部失效（无状态撤销方案）
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    sessions: Mapped[list["ChatSession"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
