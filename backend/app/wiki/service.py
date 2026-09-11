"""Wiki 空间管理：导入、扫描、增量同步、链接图重建。

设计（对齐方案 v2）：
- 受管副本：本地路径需位于 `WIKI_STORAGE_ROOT` 下，zip 解压到 `{root}/{space_id}/`；
- 幂等主键 `rel_path`；同内容 hash 视作"移动"（只改路径，不重嵌）；
- 复用 `ingest_document`（parse→chunk→embed→chunks+Qdrant）与向量清理。
"""

import hashlib
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Chunk, Document, WikiLink, WikiPage, WikiSpace
from app.rag import get_embedding_service, get_vector_store, ingest_document
from app.wiki.importer import extract_zip, safe_join
from app.wiki.links import extract_frontmatter, extract_links, slugify
from app.wiki.parser import WikiParser

logger = logging.getLogger(__name__)

# 扫描时排除的目录（Obsidian 配置/回收站/版本控制等）
_EXCLUDED_DIRS = {".obsidian", ".git", ".trash", ".stfolder", "__MACOSX"}


class WikiServiceError(Exception):
    """Wiki 业务错误（路径非法/空间不存在/无权限等）。"""


def storage_root() -> Path:
    return Path(settings.WIKI_STORAGE_ROOT).resolve()


def _scan(root: Path) -> dict[str, tuple[float, int]]:
    """扫描 vault 下的 Markdown 文件：rel_path(posix) → (mtime, size)。"""
    result: dict[str, tuple[float, int]] = {}
    for path in root.rglob("*.md"):
        rel_parts = path.relative_to(root).parts
        if any(part.startswith(".") or part in _EXCLUDED_DIRS for part in rel_parts[:-1]):
            continue
        if path.name.startswith("._"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        result[path.relative_to(root).as_posix()] = (stat.st_mtime, stat.st_size)
    return result


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
    db: AsyncSession, user_id, title: str, content: bytes, content_hash: str, extra_meta: dict
) -> Document:
    """解析→分块→嵌入→入库，返回 Document（失败置 failed 并抛错）。"""
    doc = Document(
        user_id=user_id, title=title, source_type="wiki", status="parsing", content_hash=content_hash
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


def _page_identity(rel_path: str, content: bytes):
    """页面标识：slug 以**文件名 stem** 为准（Obsidian 双链 `[[文件名]]` 按文件名匹配）；
    展示标题优先 frontmatter.title，其次 H1，再次文件名。
    """
    text = content.decode("utf-8", errors="replace")
    front, _ = extract_frontmatter(text)
    parsed = WikiParser().parse(content, meta={"wiki_path": rel_path})
    front_title = str(front.get("title") or "").strip()
    stem = Path(rel_path).stem
    title = front_title or parsed.title or stem
    slug = slugify(stem)
    return title, slug, parsed


async def _create_page(
    db: AsyncSession, user_id, space: WikiSpace, rel_path: str, content: bytes, mtime: float, size: int
) -> WikiPage:
    content_hash = hashlib.sha256(content).hexdigest()
    title, slug, parsed = _page_identity(rel_path, content)
    tags = parsed.meta.get("tags", [])
    doc = await _ingest_content(
        db, user_id, title, content, content_hash, _wiki_meta(space, rel_path, title, tags)
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
    title, slug, parsed = _page_identity(page.rel_path, content)
    tags = parsed.meta.get("tags", [])
    doc = await _ingest_content(
        db, user_id, title, content, content_hash, _wiki_meta(space, page.rel_path, title, tags)
    )
    page.title = title
    page.slug = slug
    page.document_id = doc.id
    page.content_hash = content_hash
    page.mtime = mtime
    page.size = size
    await db.commit()


async def _delete_page(db: AsyncSession, page: WikiPage) -> None:
    if page.document_id:
        doc = await db.get(Document, page.document_id)
        if doc is not None:
            await _delete_document(db, doc)
    await db.delete(page)
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
        try:
            text = (root / page.rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ref in extract_links(text):
            target_slug = slugify(ref.target)
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


async def sync_space(db: AsyncSession, user_id, space: WikiSpace) -> dict:
    """扫描→diff→摄取→链接图，返回统计。幂等，可重复调用。"""
    _assert_owner(user_id, space)
    root = Path(space.root_path).resolve()
    if not root.is_dir():
        raise WikiServiceError("空间目录不存在，请先导入 vault")

    files = _scan(root)
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
