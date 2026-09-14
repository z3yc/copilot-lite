"""Wiki 空间管理：导入、扫描、增量同步、链接图重建。

设计（对齐方案 v2）：
- 受管副本：本地路径需位于 `WIKI_STORAGE_ROOT` 下，zip 解压到 `{root}/{space_id}/`；
- 幂等主键 `rel_path`；同内容 hash 视作"移动"（只改路径，不重嵌）；
- 复用 `ingest_document`（parse→chunk→embed→chunks+Qdrant）与向量清理。
"""

import hashlib
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.obsidian.importer import extract_zip, safe_join, save_uploaded_files
from app.connectors.obsidian.links import (
    extract_frontmatter,
    extract_links,
    normalize_link_target,
    slugify,
)
from app.connectors.obsidian.parser import WikiParser
from app.core.config import settings
from app.core.soft_delete import mark_deleted
from app.models import Chunk, Document, WikiLink, WikiPage, WikiSpace
from app.rag import get_embedding_service, get_vector_store, ingest_document
from app.rag.parsers.base import decode_text

logger = logging.getLogger(__name__)

# 扫描时排除的目录（Obsidian 配置/回收站/版本控制等）
_EXCLUDED_DIRS = {".obsidian", ".git", ".trash", ".stfolder", "__MACOSX"}


def _excluded_dirs() -> set[str]:
    """基础排除目录 + 配置的额外排除目录（模板等）。"""
    extra = {d.strip() for d in settings.WIKI_EXCLUDE_DIRS.split(",") if d.strip()}
    return _EXCLUDED_DIRS | extra
# 扩展名 → 解析器 source_type（.md 走 WikiParser，含双链/标签；其余复用现有解析器）
_EXT_TYPES = {
    ".md": "wiki",
    ".markdown": "wiki",
    ".txt": "md",
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
}
_MD_EXTS = {".md", ".markdown"}


class WikiServiceError(Exception):
    """Wiki 业务错误（路径非法/空间不存在/无权限等）。"""


def storage_root() -> Path:
    return Path(settings.WIKI_STORAGE_ROOT).resolve()


def is_managed_path(path) -> bool:
    """路径是否位于受管根（WIKI_STORAGE_ROOT）之下。

    安全护栏：仅受管副本（zip/文件导入）才允许被物理删除；
    local 空间指向的是用户真实目录，**绝不 rm**。
    """
    try:
        return Path(path).resolve().is_relative_to(storage_root())
    except OSError:
        return False


def _scan(root: Path) -> tuple[dict[str, tuple[float, int]], int]:
    """扫描 vault：返回 (rel_path→(mtime,size), 被跳过的文件数)。

    支持 Markdown（含双链）以及可选的 PDF/DOCX/TXT（`WIKI_INCLUDE_NON_MD`）；
    其他扩展名计入 skipped，便于前端如实展示“未索引了多少”。
    """
    result: dict[str, tuple[float, int]] = {}
    skipped = 0
    excluded = _excluded_dirs()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part.startswith(".") or part in excluded for part in rel_parts[:-1]):
            continue
        if path.name.startswith("._"):
            continue
        ext = path.suffix.lower()
        if ext not in _EXT_TYPES or (ext not in _MD_EXTS and not settings.WIKI_INCLUDE_NON_MD):
            skipped += 1
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        result[path.relative_to(root).as_posix()] = (stat.st_mtime, stat.st_size)
    return result, skipped


async def create_space(
    db: AsyncSession,
    user_id,
    name: str,
    *,
    source_type: str = "upload",
    server_path: str | None = None,
) -> WikiSpace:
    """创建 Wiki 空间。

    - upload：使用受管目录 `{root}/{space_id}/`（由 zip 导入填充）；
    - local：server_path 必须位于 `WIKI_STORAGE_ROOT` 下（沙箱），直接登记为扫描根。
    """
    space = WikiSpace(
        owner_id=user_id, name=name.strip()[:128], source_type=source_type, root_path=""
    )
    db.add(space)
    await db.flush()  # 取得 space.id

    if source_type == "local":
        if not server_path:
            raise WikiServiceError("local 类型需要提供文件夹路径")
        candidate = Path(server_path)
        if candidate.is_absolute():
            # 绝对路径：仅本地/自托管允许（云端多用户禁止，防读任意目录）
            if not settings.WIKI_ALLOW_LOCAL_PATH:
                raise WikiServiceError(
                    "当前部署不允许使用绝对路径：请用 zip 导入，或放到受管目录下用相对路径"
                )
            path = candidate.resolve()
        else:
            # 相对路径：必须在受管根目录（WIKI_STORAGE_ROOT）内（沙箱）
            path = safe_join(storage_root(), server_path)
        if not path.is_dir():
            raise WikiServiceError("文件夹不存在或不是目录")
    else:
        path = storage_root() / str(space.id)
        path.mkdir(parents=True, exist_ok=True)

    space.root_path = str(path)
    await db.commit()
    await db.refresh(space)
    return space


async def import_zip(db: AsyncSession, user_id, space: WikiSpace, zip_bytes: bytes) -> int:
    """把 zip 解压到空间受管目录（覆盖式导入），返回写入文件数。"""
    _assert_owner(user_id, space)
    if space.source_type == "local":
        raise WikiServiceError("local 类型空间不支持 zip 导入")
    dest = Path(space.root_path)
    if dest.exists():
        shutil.rmtree(dest)
    return extract_zip(zip_bytes, dest)


async def import_files(
    db: AsyncSession, user_id, space: WikiSpace, items: list[tuple[str, bytes]]
) -> int:
    """单/多文件（可带相对路径）导入到空间受管目录，返回写入文件数。

    用于“选择文件/文件夹”入口；与 zip 导入同等的路径沙箱与限额。
    """
    _assert_owner(user_id, space)
    if space.source_type == "local":
        raise WikiServiceError("local 类型空间不支持文件导入（已在磁盘上）")
    return save_uploaded_files(Path(space.root_path), items)


async def refresh_page(db: AsyncSession, user_id, space: WikiSpace, page: WikiPage) -> None:
    """单页强制重新索引：读原件 → 重摄取 → 重建该空间链接图。"""
    _assert_owner(user_id, space)
    root = Path(space.root_path).resolve()
    path = root / page.rel_path
    if not path.is_file():
        raise WikiServiceError("原件不存在，无法重新索引")
    content = path.read_bytes()
    stat = path.stat()
    await _update_page(db, user_id, space, page, content, stat.st_mtime, stat.st_size)
    await _rebuild_links(db, user_id, space, root)


def _assert_owner(user_id, space: WikiSpace) -> None:
    if space.owner_id is not None and str(space.owner_id) != str(user_id):
        raise WikiServiceError("无权访问该空间")


async def _delete_document(db: AsyncSession, doc: Document) -> None:
    """删除文档及其分块与向量。"""
    await db.execute(sa_delete(Chunk).where(Chunk.document_id == doc.id))
    try:
        await get_vector_store().delete_by_document(doc.id)
    except Exception:
        logger.warning("Wiki 向量清理失败 document=%s", doc.id, exc_info=True)
    await db.delete(doc)
    await db.commit()


async def _ingest_content(
    db: AsyncSession,
    user_id,
    title: str,
    content: bytes,
    content_hash: str,
    extra_meta: dict,
    source_type: str = "wiki",
) -> Document:
    """解析→分块→嵌入→入库，返回 Document（失败置 failed 并抛错）。"""
    doc = Document(
        user_id=user_id,
        title=title,
        source_type=source_type,
        status="parsing",
        content_hash=content_hash,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    try:
        await ingest_document(
            db,
            doc,
            content,
            get_embedding_service(),
            get_vector_store(),
            extra_meta=extra_meta,
        )
        doc.status = "ready"
    except Exception as exc:
        doc.status = "failed"
        doc.extra = {"error": str(exc)}
        await db.commit()
        raise
    await db.commit()
    return doc


def _wiki_meta(space: WikiSpace, rel_path: str, title: str, tags: list) -> dict:
    return {
        "wiki_space": space.name,
        "wiki_path": rel_path,
        "wiki_title": title,
        "wiki_tags": tags,
    }


def _page_info(rel_path: str, content: bytes):
    """页面标识：(title, slug, source_type, parsed_or_None)。

    - slug 以**文件名 stem** 为准（Obsidian 双链按文件名匹配）；
    - 展示标题优先 frontmatter.title，其次 H1，再次文件名；
    - Markdown 走 WikiParser（含双链/标签）；其余类型复用现有解析器（source_type 映射）。
    """
    ext = Path(rel_path).suffix.lower()
    source_type = _EXT_TYPES.get(ext, "wiki")
    stem = Path(rel_path).stem
    if ext in _MD_EXTS:
        text = decode_text(content)
        front, _ = extract_frontmatter(text)
        parsed = WikiParser().parse(content, meta={"wiki_path": rel_path})
        front_title = str(front.get("title") or "").strip()
        title = front_title or parsed.title or stem
        return title, slugify(stem), source_type, parsed
    return stem, slugify(stem), source_type, None


async def _create_page(
    db: AsyncSession, user_id, space: WikiSpace, rel_path: str, content: bytes, mtime: float, size: int
) -> WikiPage:
    content_hash = hashlib.sha256(content).hexdigest()
    title, slug, source_type, parsed = _page_info(rel_path, content)
    tags = parsed.meta.get("tags", []) if parsed is not None else []
    doc = await _ingest_content(
        db,
        user_id,
        title,
        content,
        content_hash,
        _wiki_meta(space, rel_path, title, tags),
        source_type,
    )
    page = WikiPage(
        user_id=user_id,
        space_id=space.id,
        rel_path=rel_path,
        title=title,
        slug=slug,
        document_id=doc.id,
        content_hash=content_hash,
        mtime=mtime,
        size=size,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return page


async def _update_page(
    db: AsyncSession, user_id, space: WikiSpace, page: WikiPage, content: bytes, mtime: float, size: int
) -> None:
    """内容变化：删旧文档（分块+向量）后重新摄取。"""
    if page.document_id:
        old = await db.get(Document, page.document_id)
        if old is not None:
            await _delete_document(db, old)
    content_hash = hashlib.sha256(content).hexdigest()
    title, slug, source_type, parsed = _page_info(page.rel_path, content)
    tags = parsed.meta.get("tags", []) if parsed is not None else []
    doc = await _ingest_content(
        db,
        user_id,
        title,
        content,
        content_hash,
        _wiki_meta(space, page.rel_path, title, tags),
        source_type,
    )
    page.title = title
    page.slug = slug
    page.document_id = doc.id
    page.content_hash = content_hash
    page.mtime = mtime
    page.size = size
    await db.commit()


async def _delete_page(db: AsyncSession, page: WikiPage, user_id=None) -> None:
    """软删除页面（及其文档/分块/向量标记）——不物理删除，可恢复。"""
    if page.document_id:
        doc = await db.get(Document, page.document_id)
        if doc is not None and doc.deleted_at is None:
            now = datetime.now(UTC).replace(tzinfo=None)
            uid = uuid.UUID(str(user_id)) if user_id else None
            await db.execute(
                update(Chunk)
                .where(Chunk.document_id == doc.id, Chunk.deleted_at.is_(None))
                .values(deleted_at=now, deleted_by=uid)
            )
            mark_deleted(doc, user_id)
            try:
                await get_vector_store().set_deleted_by_document(doc.id, True)
            except Exception:
                logger.warning("Wiki 向量软删除标记失败 document=%s", doc.id, exc_info=True)
    mark_deleted(page, user_id)
    await db.commit()


async def _rebuild_links(
    db: AsyncSession, user_id, space: WikiSpace, root: Path
) -> None:
    """重建该空间的双链图（先清后建，页面级数据量小，全量可接受）。"""
    await db.execute(sa_delete(WikiLink).where(WikiLink.space_id == space.id))
    await db.commit()

    pages = (
        await db.scalars(select(WikiPage).where(WikiPage.space_id == space.id))
    ).all()
    slug_to_id = {page.slug: page.id for page in pages}
    rows: list[WikiLink] = []
    for page in pages:
        if Path(page.rel_path).suffix.lower() not in _MD_EXTS:
            continue  # 双链仅来自 Markdown
        try:
            text = (root / page.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ref in extract_links(text):
            target_slug = normalize_link_target(ref.target)
            rows.append(
                WikiLink(
                    user_id=user_id,
                    space_id=space.id,
                    source_page_id=page.id,
                    target_slug=target_slug,
                    target_page_id=slug_to_id.get(target_slug),
                    alias=ref.alias,
                    kind=ref.kind,
                )
            )
    if rows:
        db.add_all(rows)
    await db.commit()


async def build_graph(
    db: AsyncSession,
    user_id,
    space_id=None,
    tag: str | None = None,
    limit: int = 300,
) -> dict:
    """构建 Wiki 知识图谱：节点=页面，边=已解析双链。

    - 隔离：仅返回当前用户可访问（自有 + 共享）且未软删除空间下的未删除页面；
    - 标签：来自分块元数据 `wiki_tags`（一次查询，避免 N+1）；
    - 截断：节点数超 `limit` 时按度数降序保留，并标记 `truncated=true`。
    """
    empty = {"nodes": [], "edges": [], "total_nodes": 0, "truncated": False}

    accessible = select(WikiSpace.id).where(
        or_(WikiSpace.owner_id == user_id, WikiSpace.owner_id.is_(None)),
        WikiSpace.deleted_at.is_(None),
    )
    space_ids = set((await db.scalars(accessible)).all())
    if space_id is not None:
        try:
            space_ids &= {uuid.UUID(str(space_id))}
        except (ValueError, TypeError, AttributeError):
            return empty
    if not space_ids:
        return empty

    pages = (
        await db.scalars(
            select(WikiPage).where(
                WikiPage.space_id.in_(space_ids), WikiPage.deleted_at.is_(None)
            )
        )
    ).all()
    if not pages:
        return empty

    tags_by_doc: dict[uuid.UUID, list[str]] = {}
    doc_ids = [p.document_id for p in pages if p.document_id]
    if doc_ids:
        rows = (
            await db.execute(
                select(Chunk.document_id, Chunk.meta).where(
                    Chunk.document_id.in_(doc_ids), Chunk.deleted_at.is_(None)
                )
            )
        ).all()
        for doc_id, meta in rows:
            if doc_id not in tags_by_doc and meta:
                tags_by_doc[doc_id] = list(meta.get("wiki_tags") or [])

    def _tags(page: WikiPage) -> list[str]:
        return tags_by_doc.get(page.document_id, []) if page.document_id else []

    if tag and tag.strip():
        wanted = tag.strip()
        pages = [p for p in pages if wanted in _tags(p)]
        if not pages:
            return {**empty, "total_nodes": 0}

    page_ids = {p.id for p in pages}
    links = (
        await db.scalars(
            select(WikiLink).where(
                WikiLink.source_page_id.in_(page_ids),
                WikiLink.target_page_id.is_not(None),
            )
        )
    ).all()
    # 两端都在可见页面集合内（目标的页面可能已软删除）
    edges = [
        link
        for link in links
        if link.source_page_id in page_ids and link.target_page_id in page_ids
    ]

    degree: dict = {pid: 0 for pid in page_ids}
    for link in edges:
        degree[link.source_page_id] += 1
        degree[link.target_page_id] += 1

    space_names = {
        s.id: s.name
        for s in (
            await db.scalars(select(WikiSpace).where(WikiSpace.id.in_(space_ids)))
        ).all()
    }

    total_nodes = len(pages)
    cap = max(1, limit)
    kept = sorted(pages, key=lambda p: (-degree.get(p.id, 0), p.title))[:cap]
    kept_ids = {p.id for p in kept}

    return {
        "nodes": [
            {
                "id": str(p.id),
                "title": p.title,
                "slug": p.slug,
                "space_id": str(p.space_id),
                "space": space_names.get(p.space_id),
                "degree": degree.get(p.id, 0),
                "tags": _tags(p),
            }
            for p in kept
        ],
        "edges": [
            {
                "source": str(link.source_page_id),
                "target": str(link.target_page_id),
                "kind": link.kind,
                "relation": link.relation,
            }
            for link in edges
            if link.source_page_id in kept_ids and link.target_page_id in kept_ids
        ],
        "total_nodes": total_nodes,
        "truncated": total_nodes > cap,
    }


async def sync_space(db: AsyncSession, user_id, space: WikiSpace) -> dict:
    """扫描→diff→摄取→链接图，返回统计。幂等，可重复调用。"""
    _assert_owner(user_id, space)
    root = Path(space.root_path).resolve()
    if not root.is_dir():
        raise WikiServiceError("空间目录不存在，请先导入 vault")

    files, skipped = _scan(root)
    existing = (
        await db.scalars(select(WikiPage).where(WikiPage.space_id == space.id))
    ).all()
    pages = {page.rel_path: page for page in existing}
    by_hash = {page.content_hash: page for page in existing if page.content_hash}

    stats = {
        "added": 0,
        "updated": 0,
        "moved": 0,
        "deleted": 0,
        "failed": 0,
        "skipped": skipped,
        "total": len(files),
    }
    seen: set[str] = set()

    for rel_path in sorted(files):
        mtime, size = files[rel_path]
        seen.add(rel_path)
        try:
            content = (root / rel_path).read_bytes()
        except OSError:
            stats["failed"] += 1
            continue
        content_hash = hashlib.sha256(content).hexdigest()
        page = pages.get(rel_path)

        if page is None:
            moved_page = by_hash.get(content_hash)
            if moved_page is not None and moved_page.rel_path not in files:
                # 内容未变、路径变化 → 视为移动，仅更新路径（不重嵌）
                moved_page.rel_path = rel_path
                moved_page.mtime = mtime
                moved_page.size = size
                await db.commit()
                stats["moved"] += 1
                continue
            try:
                new_page = await _create_page(db, user_id, space, rel_path, content, mtime, size)
                by_hash[content_hash] = new_page
                stats["added"] += 1
            except Exception:
                logger.warning("Wiki 页面摄取失败: %s", rel_path, exc_info=True)
                stats["failed"] += 1
            continue

        if page.content_hash != content_hash:
            try:
                await _update_page(db, user_id, space, page, content, mtime, size)
                stats["updated"] += 1
            except Exception:
                logger.warning("Wiki 页面更新失败: %s", rel_path, exc_info=True)
                stats["failed"] += 1
        elif page.mtime != mtime or page.size != size:
            page.mtime = mtime
            page.size = size
            await db.commit()

    for rel_path, page in pages.items():
        if rel_path not in seen:
            await _delete_page(db, page)
            stats["deleted"] += 1

    await _rebuild_links(db, user_id, space, root)
    # 列为 TIMESTAMP WITHOUT TIME ZONE（naive）：必须去除时区，否则 asyncpg 报错
    space.last_synced_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    logger.info("Wiki 同步完成 space=%s stats=%s", space.name, stats)
    return stats
