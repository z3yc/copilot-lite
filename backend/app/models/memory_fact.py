"""长期记忆模型：会话中提取的用户事实与偏好。

- 文本存 PostgreSQL（管理/展示）；
- 向量存 Qdrant memory 集合（语义召回）。
"""

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin

# 记忆类别
CATEGORY_PREFERENCE = "preference"  # 偏好（喜欢简洁回答等）
CATEGORY_FACT = "fact"  # 事实（在准备面试、住在北京等）
CATEGORY_BACKGROUND = "background"  # 背景（职业、兴趣等）


class MemoryFact(SoftDeleteMixin, Base):
    __tablename__ = "memory_facts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    fact: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default=CATEGORY_FACT)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    # 来源会话（可空：用户手动/旧数据）
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
