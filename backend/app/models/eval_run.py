"""评测运行模型：作业状态机（ADMIN_PLAN §3 / §6 / §9 N0.5）。

- 承担"页面触发评测"的作业状态机：queued → running → done/failed；
- 指标带配置指纹（config_fingerprint），历史数字可比（§2.5）；
- 预留 tenant_id / workspace_id 多租户接缝；
- `dataset_id` 暂不设外键（golden_datasets 在 N2.1 引入），先留字段。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# 作业状态
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# 触发来源
TRIGGER_MANUAL = "manual"
TRIGGER_CI = "ci"


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # 数据集（N2.1 建 golden_datasets 后补外键）；可空兼容临时/全量评测
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_QUEUED, index=True)
    trigger: Mapped[str] = mapped_column(String(16), default=TRIGGER_MANUAL)
    # 来源切片：all / docs / wiki（per-source 出数）
    source_scope: Mapped[str] = mapped_column(String(16), default="all")
    # 配置指纹：engine/model/prompt_version/embedding_model/top_k/...（§2.5）
    config_fingerprint: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # 企业多租户接缝（默认 null）
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
