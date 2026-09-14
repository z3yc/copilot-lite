"""审计日志模型：append-only，记录敏感 / 管理操作（ADMIN_PLAN §3 / AGENTS §15）。

- 只追加，不提供更新 / 删除入口（审计追溯依据）；
- ``user_id`` 不设外键：用户软删 / 注销后仍需保留历史审计；
- ``tenant_id`` / ``workspace_id`` 为多租户预留接缝（默认 null，查询带过滤后
  即可平滑切换多租户，ADMIN_PLAN §7）。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 结果口径：ok（成功）/ denied（越权拒绝）/ error（执行失败）
    result: Mapped[str] = mapped_column(String(16), default="ok")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    # 企业多租户接缝（默认 null）
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
