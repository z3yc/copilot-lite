"""Wiki 导入：zip 安全解压 + 路径沙箱。

安全（§6）：
- 路径沙箱：解压目标 resolve 后必须位于受管根内，拒绝 `..` / 绝对路径条目；
- 防 zip 炸弹：限制压缩包大小、文件数、解压后总大小；
- 过滤 macOS 元数据目录 `__MACOSX/` 与 `._*` 文件。
"""

import io
import zipfile
from pathlib import Path

from app.core.config import settings


class WikiImportError(Exception):
    """Wiki 导入失败（超限/非法路径等）。"""


def safe_join(root: Path, rel: str) -> Path:
    """把相对路径拼到 root 下，并校验未越界（拒绝 .. / 绝对路径）。"""
    resolved_root = Path(root).resolve()
    target = (resolved_root / rel).resolve()
    if not target.is_relative_to(resolved_root):
        raise WikiImportError(f"非法路径（越界）: {rel}")
    return target


def extract_zip(zip_bytes: bytes, dest: Path) -> int:
    """安全解压 zip 到 dest，返回写入的文件数。"""
    if len(zip_bytes) > settings.WIKI_MAX_ARCHIVE_BYTES:
        raise WikiImportError(
            f"压缩包超过上限 {settings.WIKI_MAX_ARCHIVE_BYTES // 1024 // 1024}MB"
        )

    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    written = 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise WikiImportError("不是有效的 zip 文件") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > settings.WIKI_MAX_FILES:
            raise WikiImportError(f"文件数超过上限 {settings.WIKI_MAX_FILES}")

        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            if name.startswith("__MACOSX/") or Path(name).name.startswith("._"):
                continue  # macOS 元数据
            target = safe_join(dest, name)
            written += 1
            if written > settings.WIKI_MAX_FILES:
                raise WikiImportError(f"文件数超过上限 {settings.WIKI_MAX_FILES}")
            total_bytes += info.file_size
            if total_bytes > settings.WIKI_MAX_EXTRACT_BYTES:
                raise WikiImportError(
                    f"解压后超过上限 {settings.WIKI_MAX_EXTRACT_BYTES // 1024 // 1024}MB"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as out:
                out.write(src.read())

    return written
