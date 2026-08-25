"""文档分块模型：解析后的最小检索单元。

- 文本与元数据存 PostgreSQL（BM25 关键词检索 + 引用溯源）；
- 向量存 Qdrant（vector_id 关联），两者通过 vector_id 映射。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)  # 文档内顺序
    content: Mapped[str] = mapped_column(Text)
    # 元数据：标题路径 / 页码 / 来源类型等，用于引用溯源与过滤
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    # Qdrant 中的 point id（字符串化 UUID），用于删除/同步
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
