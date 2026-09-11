"""待办模型：个人管理工具的数据载体。

扩展（分类 + 标签）：
- category_id：关联 categories 表（默认 4 类，预留自定义）
- tags：自由文本标签（JSON 数组）
"""

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin


class Todo(SoftDeleteMixin, Base):
    __tablename__ = "todos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / done
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 最高 - 5 最低
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 分类（可空；默认 4 类：工作/生活/学习/其他）
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 自由标签
    tags: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
