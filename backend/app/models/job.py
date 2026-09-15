"""通用后台作业模型（OPTIMIZATION_PLAN 批次 J1）。

定位：把「慢且可离线」的摄取/同步从 HTTP 请求里摘出来——
请求只建作业并立即返回 `job_id`，后台 worker 执行，前端轮询进度。

- 状态机：`queued → running → done`；失败按 `max_attempts` 重试，耗尽置 `dead`（死信）；
- `payload` / `result` 为 JSON：载荷与产物随 `kind` 变化，机制层不感知业务；
- 预留 `tenant_id` / `workspace_id` 多租户接缝（ADMIN_PLAN §7）；
- 作业是**运维记录**：不提供删除接口，保留用于排查与审计（AGENTS §13 的软删除
  约束针对业务/用户数据；此处无删除语义）。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# 作业状态：排队 / 执行中 / 完成 / 失败（可重试的中间态）/ 死信（重试耗尽）
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_DEAD = "dead"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # 作业类型（业务方注册 handler 的键，如 wiki_sync）
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_QUEUED, index=True)
    # 归属用户：作业同样受用户隔离（AGENTS §6.3）
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 企业多租户接缝（默认 null）
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
