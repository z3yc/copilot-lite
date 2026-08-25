"""待办分类模型：预留用户自定义能力，第一版 seed 固定 4 类。"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# 默认分类（注册/补齐时 seed）
DEFAULT_CATEGORIES = [
    {"name": "工作", "color": "#4f6ef7", "sort_order": 0},
    {"name": "生活", "color": "#2f9e44", "sort_order": 1},
    {"name": "学习", "color": "#f08c00", "sort_order": 2},
    {"name": "其他", "color": "#8a90a3", "sort_order": 3},
]


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16), default="#8a90a3")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
