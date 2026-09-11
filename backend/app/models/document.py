"""文档模型：知识库的顶层实体（原件元数据）。

向量相关的 Chunk/Embedding 模型将在 P2（知识库阶段）引入。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32))  # md / pdf / docx / code / web
    # 内容 SHA-256：同用户同内容去重，避免重复向量（可空：历史数据）
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="uploaded")  # uploaded/parsing/ready/failed
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
