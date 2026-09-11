"""Obsidian Wiki 语法解析：frontmatter / 双链 / 标签。

- `[[目标]]`、`[[目标|别名]]`、`[[目标#标题]]` → link
- `![[目标]]` → embed
- `#标签` → tag
- 代码块内内容不参与解析（避免把示例 `[[ ]]` 当链接）
"""

import re
from dataclasses import dataclass

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
# 目标不含 [ ] | #；可选 #标题；可选 |别名；前缀 ! 表示嵌入
_WIKILINK_RE = re.compile(
    r"(!?)\[\[([^\[\]\|#]+?)(?:#([^\[\]\|]+?))?(?:\|([^\[\]]+?))?\]\]"
)
_TAG_RE = re.compile(r"(?:^|\s)#([\w\u4e00-\u9fff\-/]+)")


@dataclass
class WikiLinkRef:
    target: str
    alias: str | None
    kind: str  # link / embed


def strip_code_blocks(text: str) -> str:
    """移除围栏代码块，避免其中示例语法被误判为链接/标签。"""
    return _FENCE_RE.sub("", text)


def extract_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter（极简实现，支持 key: value、内联数组、短横线数组）。

    不引入 PyYAML 依赖：Obsidian frontmatter 常用字段（title/tags/aliases）足够。
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    return _parse_simple_yaml(match.group(1)), text[match.end() :]


def _parse_simple_yaml(block: str) -> dict:
    meta: dict = {}
    current_key: str | None = None
    for raw in block.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_key:
            value = stripped[2:].strip().strip("\"'")
            existing = meta.get(current_key)
            if not isinstance(existing, list):
                existing = [] if existing in (None, "") else [existing]
                meta[current_key] = existing
            existing.append(value)
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            current_key = key
            if value.startswith("[") and value.endswith("]"):
                meta[key] = [
                    item.strip().strip("\"'")
                    for item in value[1:-1].split(",")
                    if item.strip()
                ]
            elif value:
                meta[key] = value.strip("\"'")
            else:
                meta[key] = []
    return meta


def extract_links(text: str) -> list[WikiLinkRef]:
    """提取双链（跳过代码块）。"""
    body = strip_code_blocks(text)
    refs: list[WikiLinkRef] = []
    for match in _WIKILINK_RE.finditer(body):
        embed, target, _heading, alias = match.groups()
        cleaned = target.strip()
        if not cleaned:
            continue
        refs.append(
            WikiLinkRef(
                target=cleaned,
                alias=alias.strip() if alias else None,
                kind="embed" if embed else "link",
            )
        )
    return refs


def extract_tags(text: str) -> list[str]:
    """提取 #标签（去重，保持出现顺序）。"""
    body = strip_code_blocks(text)
    seen: set[str] = set()
    tags: list[str] = []
    for match in _TAG_RE.finditer(body):
        tag = match.group(1)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def slugify(title: str) -> str:
    """标题归一化（用于双链目标匹配）：小写、空白转连字符、去除特殊字符。"""
    text = title.strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^0-9a-z\-\u4e00-\u9fff]", "", text)
    return text.strip("-") or "untitled"


# 可被 Obsidian 双链显式带上的文档扩展名（归一化时剥离，链接按文件名解析）
_DOC_EXTS = (".markdown", ".md", ".txt", ".pdf", ".docx", ".doc")


def normalize_link_target(target: str) -> str:
    """按 Obsidian 解析规则归一化双链目标，再 slugify 以匹配页面 slug（文件名）。

    Obsidian 链接可带子目录路径（`folder/Note`）、显式扩展名（`Note.md`）、
    块引用（`Note^block`）、锚点（`Note#Heading`）。Obsidian 最终按**文件名**
    （去扩展名）解析，所以这里取 basename 并剥离已知扩展名，避免出现
    `foldernote` / `notemd` 这类与页面 slug 不匹配的悬空链接。
    """
    text = (target or "").strip()
    if not text:
        return "untitled"
    # 锚点 # / 块引用 ^ 均不参与文件名匹配（# 通常已被 extract_links 单独捕获）
    text = text.split("#", 1)[0].split("^", 1)[0].strip()
    # basename：兼容 / 与 \\ 两种路径分隔符
    text = text.replace("\\", "/").rsplit("/", 1)[-1].strip()
    low = text.lower()
    for ext in _DOC_EXTS:
        if low.endswith(ext):
            text = text[: -len(ext)]
            break
    return slugify(text)
