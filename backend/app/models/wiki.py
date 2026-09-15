"""Wiki 模型：Obsidian vault 导入后的空间 / 页面 / 链接图索引。

设计要点：
- `wiki_space`：一个导入的 vault（`owner_id` 可空 = 共享空间）；
- `wiki_page`：vault 内一个 Markdown 页面（`rel_path` 幂等主键），
  关联到 `documents`（复用分块/向量/检索链路）；
- `wiki_link`：双链图（正向 + 反向），`target_page_id` 为空表示悬空链接。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin


class WikiSpace(SoftDeleteMixin, Base):
    __tablename__ = "wiki_spaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # 归属用户；NULL 表示共享空间
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    # upload（zip 导入，解压到受管根）/ local（受管根下的服务器路径）
    source_type: Mapped[str] = mapped_column(String(16), default="upload")
    # 实际扫描根目录（受管副本路径；沙箱校验）
    root_path: Mapped[str] = mapped_column(String(512))
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WikiPage(SoftDeleteMixin, Base):
    __tablename__ = "wiki_pages"
    __table_args__ = (
        UniqueConstraint("space_id", "rel_path", name="uq_wiki_page_space_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wiki_spaces.id", ondelete="CASCADE"), index=True
    )
    rel_path: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    # 关联摄取文档（删除文档时置空，页面索引保留）
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mtime: Mapped[float] = mapped_column(Float, default=0.0)
    size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class WikiLink(Base):
    __tablename__ = "wiki_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wiki_spaces.id", ondelete="CASCADE"), index=True
    )
    source_page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wiki_pages.id", ondelete="CASCADE"), index=True
    )
    target_slug: Mapped[str] = mapped_column(String(255), index=True)
    target_page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="link")  # link / embed / tag
    # 轻量本体用（M4 可选）：关系类型；未启用时为空
    relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
