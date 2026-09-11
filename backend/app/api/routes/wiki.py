"""Wiki 接口：空间管理 / zip 导入 / 增量同步 / 页面浏览。

- POST   /wiki/spaces                     创建空间
- GET    /wiki/spaces                     空间列表
- DELETE /wiki/spaces/{id}                删除空间（含页面/分块/向量）
- POST   /wiki/spaces/{id}/import         上传 zip 导入 vault（并同步）
- POST   /wiki/spaces/{id}/sync           手动同步
- GET    /wiki/pages                      页面列表（分页 + 搜索）
- GET    /wiki/pages/{id}                 页面详情（正文 + 出链/反向链接）
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, parse_uuid
from app.core.config import settings
from app.core.db import get_session
from app.core.pagination import DEFAULT_PAGE_SIZE, PageOut, normalize_page, page_offset
from app.models import Chunk, User, WikiLink, WikiPage, WikiSpace
from app.wiki.importer import WikiImportError
from app.wiki.service import (
    WikiServiceError,
    _delete_page,
    create_space,
    import_zip,
    sync_space,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wiki", tags=["wiki"])


# ---------------- Schemas ----------------


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    source_type: str = Field(default="upload", pattern="^(upload|local)$")
    server_path: str | None = None  # local 类型：WIKI_STORAGE_ROOT 下的相对路径


class SpaceOut(BaseModel):
    id: str
    name: str
    source_type: str
    page_count: int = 0
    last_synced_at: datetime | None = None


class WikiPageOut(BaseModel):
    id: str
    space_id: str
    space_name: str | None = None
    rel_path: str
    title: str
    slug: str
    document_id: str | None = None


class LinkOut(BaseModel):
    target_slug: str
    target_page_id: str | None = None
    alias: str | None = None
    kind: str


class BacklinkOut(BaseModel):
    source_page_id: str
    source_title: str | None = None


class PageDetail(WikiPageOut):
    content: str = ""
    tags: list[str] = []
    links: list[LinkOut] = []
    backlinks: list[BacklinkOut] = []


class SyncResult(BaseModel):
    added: int
    updated: int
    moved: int
    deleted: int
    failed: int
    total: int
    imported_files: int | None = None


# ---------------- Helpers ----------------


def _space_out(space: WikiSpace, page_count: int = 0) -> SpaceOut:
    return SpaceOut(
        id=str(space.id),
        name=space.name,
        source_type=space.source_type,
        page_count=page_count,
        last_synced_at=space.last_synced_at,
    )


async def _get_space(db: AsyncSession, space_id: str, user: User) -> WikiSpace:
    space = await db.get(WikiSpace, parse_uuid(space_id))
    # owner 为空 = 共享空间
    if space is None or (space.owner_id is not None and space.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Wiki 空间不存在")
    return space


def _ensure_enabled() -> None:
    if not settings.WIKI_ENABLED:
        raise HTTPException(status_code=503, detail="Wiki 功能未启用")


# ---------------- 空间 ----------------


@router.post("/spaces", response_model=SpaceOut)
async def create_wiki_space(
    req: SpaceCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SpaceOut:
    """创建 Wiki 空间（upload：待 zip 导入；local：登记受管根下的服务器目录）。"""
    _ensure_enabled()
    try:
        space = await create_space(
            db,
            user.id,
            req.name,
            source_type=req.source_type,
            server_path=req.server_path,
        )
    except WikiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _space_out(space)


@router.get("/spaces", response_model=list[SpaceOut])
async def list_wiki_spaces(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SpaceOut]:
    """当前用户可见的 Wiki 空间（含共享空间）。"""
    stmt = select(WikiSpace).where(
        or_(WikiSpace.owner_id == user.id, WikiSpace.owner_id.is_(None))
    )
    spaces = (await db.scalars(stmt)).all()
    counts = dict(
        (
            await db.execute(
                select(WikiPage.space_id, func.count())
                .where(WikiPage.space_id.in_([s.id for s in spaces]))
                .group_by(WikiPage.space_id)
            )
        ).all()
    ) if spaces else {}
    return [_space_out(s, counts.get(s.id, 0)) for s in spaces]


@router.delete("/spaces/{space_id}")
async def delete_wiki_space(
    space_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除空间：级联清理页面/分块/向量/链接与受管副本目录。"""
    space = await _get_space(db, space_id, user)
    pages = (
        await db.scalars(select(WikiPage).where(WikiPage.space_id == space.id))
    ).all()
    for page in pages:
        await _delete_page(db, page)
    await db.delete(space)
    await db.commit()
    try:
        shutil.rmtree(Path(space.root_path), ignore_errors=True)
    except OSError:
        logger.warning("Wiki 目录清理失败: %s", space.root_path, exc_info=True)
    return {"deleted": space_id}


# ---------------- 导入 / 同步 ----------------


@router.post("/spaces/{space_id}/import", response_model=SyncResult)
async def import_wiki_zip(
    space_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SyncResult:
    """上传 Obsidian vault 的 zip 包：解压到受管副本后立即同步。"""
    _ensure_enabled()
    space = await _get_space(db, space_id, user)
    content = await file.read(settings.WIKI_MAX_ARCHIVE_BYTES + 1)
    if len(content) > settings.WIKI_MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="压缩包过大")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        imported = await import_zip(db, user.id, space, content)
    except (WikiImportError, WikiServiceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stats = await _sync(db, user, space)
    return SyncResult(**stats, imported_files=imported)


@router.post("/spaces/{space_id}/sync", response_model=SyncResult)
async def sync_wiki_space(
    space_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SyncResult:
    """手动同步：扫描受管副本并增量更新索引。"""
    _ensure_enabled()
    space = await _get_space(db, space_id, user)
    stats = await _sync(db, user, space)
    return SyncResult(**stats)


async def _sync(db: AsyncSession, user: User, space: WikiSpace) -> dict:
    try:
        return await sync_space(db, user.id, space)
    except WikiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------- 页面 ----------------


def _page_out(page: WikiPage, space_name: str | None = None) -> WikiPageOut:
    return WikiPageOut(
        id=str(page.id),
        space_id=str(page.space_id),
        space_name=space_name,
        rel_path=page.rel_path,
        title=page.title,
        slug=page.slug,
        document_id=str(page.document_id) if page.document_id else None,
    )


@router.get("/pages", response_model=PageOut[WikiPageOut])
async def list_wiki_pages(
    space: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PageOut[WikiPageOut]:
    """页面列表（分页，可按空间/标题搜索）。"""
    space_ids = (
        await db.scalars(
            select(WikiSpace.id).where(
                or_(WikiSpace.owner_id == user.id, WikiSpace.owner_id.is_(None))
            )
        )
    ).all()
    stmt = select(WikiPage).where(WikiPage.space_id.in_(space_ids))
    if space:
        stmt = stmt.where(WikiPage.space_id == parse_uuid(space))
    if q and q.strip():
        stmt = stmt.where(WikiPage.title.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(WikiPage.title)

    page, page_size = normalize_page(page, page_size)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset, limit = page_offset(page, page_size)
    rows = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    names = {
        s.id: s.name
        for s in (
            await db.scalars(select(WikiSpace).where(WikiSpace.id.in_(space_ids)))
        ).all()
    }
    return PageOut(
        items=[_page_out(r, names.get(r.space_id)) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/pages/{page_id}", response_model=PageDetail)
async def get_wiki_page(
    page_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PageDetail:
    """页面详情：正文（只读）+ frontmatter 标签 + 出链/反向链接。"""
    wp = await db.get(WikiPage, parse_uuid(page_id))
    if wp is None:
        raise HTTPException(status_code=404, detail="Wiki 页面不存在")
    space = await db.get(WikiSpace, wp.space_id)
    if space is None or (space.owner_id is not None and space.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Wiki 页面不存在")

    content = ""
    try:
        content = (Path(space.root_path) / wp.rel_path).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        content = ""

    tags: list[str] = []
    if wp.document_id:
        meta = await db.scalar(
            select(Chunk.meta).where(Chunk.document_id == wp.document_id).limit(1)
        )
        if meta:
            tags = list(meta.get("wiki_tags") or [])

    outgoing = (
        await db.scalars(select(WikiLink).where(WikiLink.source_page_id == wp.id))
    ).all()
    backlinks_rows = (
        await db.scalars(select(WikiLink).where(WikiLink.target_page_id == wp.id))
    ).all()
    source_titles = {
        p.id: p.title
        for p in (
            await db.scalars(
                select(WikiPage).where(
                    WikiPage.id.in_([link.source_page_id for link in backlinks_rows])
                )
            )
        ).all()
    } if backlinks_rows else {}

    detail = PageDetail(
        **_page_out(wp, space.name).model_dump(),
        content=content,
        tags=tags,
        links=[
            LinkOut(
                target_slug=link.target_slug,
                target_page_id=str(link.target_page_id) if link.target_page_id else None,
                alias=link.alias,
                kind=link.kind,
            )
            for link in outgoing
        ],
        backlinks=[
            BacklinkOut(
                source_page_id=str(link.source_page_id),
                source_title=source_titles.get(link.source_page_id),
            )
            for link in backlinks_rows
        ],
    )
    return detail
