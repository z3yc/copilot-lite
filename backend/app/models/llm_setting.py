"""用户模型配置：按用户覆盖 LLM 的 API Key / Base URL / 模型等。

- 每个用户至多一条；有配置则用配置，否则回退环境变量（`.env`）。
- `api_key_encrypted` 存密文（见 core/crypto.py），接口不回传明文。
"""

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# 默认值（与环境变量默认一致，便于前端回显）
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class LLMSetting(Base):
    __tablename__ = "llm_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    base_url: Mapped[str] = mapped_column(String(255), default=DEFAULT_BASE_URL)
    model: Mapped[str] = mapped_column(String(128), default=DEFAULT_MODEL)
    # 加密后的 API Key（Fernet）；空表示未配置
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
