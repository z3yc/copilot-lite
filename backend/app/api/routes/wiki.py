"""Wiki 接口：空间管理 / zip 导入 / 增量同步 / 页面浏览。

- POST   /wiki/spaces                     创建空间
- GET    /wiki/spaces                     空间列表
- DELETE /wiki/spaces/{id}                删除空间（含页面/分块/向量）
- POST   /wiki/spaces/{id}/import         上传 zip 导入 vault（并同步）
- POST   /wiki/spaces/{id}/sync           手动同步
- GET    /wiki/pages                      页面列表（分页 + 搜索）
- GET    /wiki/pages/{id}                 页面详情（正文 + 出链/反向链接）
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, parse_uuid
from app.connectors.base import get_connector
from app.connectors.obsidian import connector as _obsidian_connector  # noqa: F401  导入即注册
from app.connectors.obsidian.importer import WikiImportError
from app.connectors.obsidian.service import (
    WikiServiceError,
    _delete_page,
    refresh_page,
)
from app.core.config import settings
from app.core.db import get_session
from app.core.pagination import DEFAULT_PAGE_SIZE, PageOut, normalize_page, page_offset
from app.core.soft_delete import mark_deleted
from app.models import Chunk, Document, User, WikiLink, WikiPage, WikiSpace

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
    page_type: str = "md"  # md / pdf / docx / txt


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
    document_status: str | None = None  # ready / parsing / failed（供重试提示）


class SyncResult(BaseModel):
    added: int
    updated: int
    moved: int
    deleted: int
    failed: int
    total: int
    skipped: int = 0  # 未索引的无关文件数（不支持的扩展名）
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
    # owner 为空 = 共享空间；已软删除不可见
    if (
        space is None
        or space.deleted_at is not None
        or (space.owner_id is not None and space.owner_id != user.id)
    ):
        raise HTTPException(status_code=404, detail="Wiki 空间不存在")
    return space


def _connector():
    """取 Obsidian 连接器（企业落地：换来源只需换连接器）。"""
    return get_connector("obsidian")


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
        space = await _connector().create_space(
            db,
            user.id,
            req.name,
            server_path=req.server_path,
            source_type=req.source_type,
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
        or_(WikiSpace.owner_id == user.id, WikiSpace.owner_id.is_(None)),
        WikiSpace.deleted_at.is_(None),
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
    """删除空间（软删除：页面/文档/向量标记，不物理删副本，可恢复）。"""
    space = await _get_space(db, space_id, user)
    pages = (
        await db.scalars(
            select(WikiPage).where(
                WikiPage.space_id == space.id, WikiPage.deleted_at.is_(None)
            )
        )
    ).all()
    for page in pages:
        await _delete_page(db, page, user.id)
    mark_deleted(space, user.id)
    await db.commit()
    # 软删除：不物理删除受管副本/外部目录（可恢复）；索引向量已标记 deleted
    logger.info("Wiki 空间已软删除: %s", space_id)
    return {"deleted": space_id, "soft": True}


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
        imported = await _connector().import_archive(db, user.id, space, content)
    except (WikiImportError, WikiServiceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stats = await _sync(db, user, space)
    return SyncResult(**stats, imported_files=imported)


@router.post("/spaces/{space_id}/import-files", response_model=SyncResult)
async def import_wiki_files(
    space_id: str,
    files: list[UploadFile] = File(...),
    paths: str = Form("[]"),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SyncResult:
    """上传单/多文件（或文件夹，带相对路径）到 Wiki 空间后同步。

    paths：与 files 同序的 JSON 数组（相对路径），用于保留文件夹结构；缺省用文件名。
    """
    _ensure_enabled()
    space = await _get_space(db, space_id, user)
    try:
        rel_paths = json.loads(paths) if paths else []
    except (ValueError, TypeError):
        rel_paths = []
    if not isinstance(rel_paths, list):
        rel_paths = []

    items: list[tuple[str, bytes]] = []
    for i, upload in enumerate(files):
        data = await upload.read(settings.WIKI_MAX_EXTRACT_BYTES + 1)
        if len(data) > settings.WIKI_MAX_EXTRACT_BYTES:
            raise HTTPException(status_code=413, detail=f"文件过大: {upload.filename}")
        rel = (
            str(rel_paths[i])
            if i < len(rel_paths) and rel_paths[i]
            else (upload.filename or f"file-{i}")
        )
        items.append((rel, data))
    if not items:
        raise HTTPException(status_code=400, detail="未收到文件")
    try:
        imported = await _connector().import_files(db, user.id, space, items)
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
        return await _connector().sync(db, user.id, space)
    except WikiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/spaces/{space_id}/resolve")
async def resolve_wiki_page(
    space_id: str,
    slug: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """按 slug 解析 Wiki 页面（供前端点击 `[[双链]]` 跳转）。"""
    space = await _get_space(db, space_id, user)
    page = await db.scalar(
        select(WikiPage)
        .where(
            WikiPage.space_id == space.id,
            WikiPage.slug == slug,
            WikiPage.deleted_at.is_(None),
        )
        .limit(1)
    )
    if page is None:
        raise HTTPException(status_code=404, detail="页面不存在")
    return {"page_id": str(page.id), "title": page.title}


# ---------------- 页面 ----------------


def _page_out(page: WikiPage, space_name: str | None = None) -> WikiPageOut:
    ext = Path(page.rel_path).suffix.lower().lstrip(".")
    page_type = {"markdown": "md", "doc": "docx"}.get(ext, ext or "md")
    return WikiPageOut(
        id=str(page.id),
        space_id=str(page.space_id),
        space_name=space_name,
        rel_path=page.rel_path,
        title=page.title,
        slug=page.slug,
        document_id=str(page.document_id) if page.document_id else None,
        page_type=page_type,
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
                or_(WikiSpace.owner_id == user.id, WikiSpace.owner_id.is_(None)),
                WikiSpace.deleted_at.is_(None),
            )
        )
    ).all()
    stmt = select(WikiPage).where(
        WikiPage.space_id.in_(space_ids), WikiPage.deleted_at.is_(None)
    )
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
    if wp is None or wp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Wiki 页面不存在")
    space = await db.get(WikiSpace, wp.space_id)
    if (
        space is None
        or space.deleted_at is not None
        or (space.owner_id is not None and space.owner_id != user.id)
    ):
        raise HTTPException(status_code=404, detail="Wiki 页面不存在")
    return await _build_page_detail(db, space, wp)


async def _build_page_detail(
    db: AsyncSession, space: WikiSpace, wp: WikiPage
) -> PageDetail:
    """组装页面详情（正文/标签/出链/反向链接/文档状态）。"""
    content = ""
    ext = Path(wp.rel_path).suffix.lower()
    if ext in {".md", ".markdown", ".txt"}:
        try:
            content = (Path(space.root_path) / wp.rel_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            content = ""
    elif wp.document_id:
        # 非文本（PDF/DOCX）：展示已抽取的分块文本
        chunk_rows = (
            await db.scalars(
                select(Chunk)
                .where(Chunk.document_id == wp.document_id)
                .order_by(Chunk.chunk_index)
            )
        ).all()
        content = "\n\n".join(c.content for c in chunk_rows)

    tags: list[str] = []
    document_status: str | None = None
    if wp.document_id:
        meta = await db.scalar(
            select(Chunk.meta).where(Chunk.document_id == wp.document_id).limit(1)
        )
        if meta:
            tags = list(meta.get("wiki_tags") or [])
        doc = await db.get(Document, wp.document_id)
        if doc is not None:
            document_status = doc.status

    outgoing = (
        await db.scalars(select(WikiLink).where(WikiLink.source_page_id == wp.id))
    ).all()
    backlinks_rows = (
        await db.scalars(select(WikiLink).where(WikiLink.target_page_id == wp.id))
    ).all()
    source_titles = (
        {
            p.id: p.title
            for p in (
                await db.scalars(
                    select(WikiPage).where(
                        WikiPage.id.in_([link.source_page_id for link in backlinks_rows])
                    )
                )
            ).all()
        }
        if backlinks_rows
        else {}
    )

    return PageDetail(
        **_page_out(wp, space.name).model_dump(),
        content=content,
        tags=tags,
        document_status=document_status,
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


@router.post("/pages/{page_id}/sync", response_model=PageDetail)
async def resync_wiki_page(
    page_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PageDetail:
    """单页重新索引（失败/内容变更时无需全量同步）。"""
    wp = await db.get(WikiPage, parse_uuid(page_id))
    if wp is None or wp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Wiki 页面不存在")
    space = await db.get(WikiSpace, wp.space_id)
    if (
        space is None
        or space.deleted_at is not None
        or (space.owner_id is not None and space.owner_id != user.id)
    ):
        raise HTTPException(status_code=404, detail="Wiki 页面不存在")
    try:
        await refresh_page(db, user.id, space, wp)
    except WikiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _build_page_detail(db, space, wp)
