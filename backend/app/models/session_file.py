"""会话附件模型：对话中上传的文件，仅存在于本次会话。

与知识库（documents/chunks）完全隔离：
- 附件文本存于此表，对话时注入上下文；
- 不影响全局知识库检索。
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SessionFile(Base):
    __tablename__ = "session_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)  # 提取后的文本（已截断存储）
    # 原始文件字节数（size 字段语义如实：解析文本长度 ≠ 文件大小）
    bytes_size: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
