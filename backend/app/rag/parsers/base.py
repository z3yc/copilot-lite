"""文档解析器抽象：统一的解析结果结构与注册机制。

解析器职责：把原始文件内容 → 结构化章节列表（标题层级 + 文本 + 元数据），
供分块模块（chunking）消费。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Section:
    """文档中的一节（带标题层级，供智能分块锚定边界）。"""

    heading: str | None  # 章节标题
    level: int  # 标题层级（1-6，无标题为 0）
    content: str  # 正文文本
    page: int | None = None  # 页码（PDF 等分页格式）
    meta: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """解析结果：文档元信息 + 章节列表。"""

    title: str
    source_type: str  # md / pdf / docx / code / web
    sections: list[Section]
    meta: dict = field(default_factory=dict)


class DocumentParser(ABC):
    """解析器基类：子类实现 parse()，并注册 source_type。"""

    source_type: str = ""

    @abstractmethod
    def parse(self, content: bytes, meta: dict | None = None) -> ParsedDocument:
        """解析原始字节内容为结构化文档。"""


def decode_text(content: bytes) -> str:
    """稳健文本解码：处理 UTF-16/BOM/GBK 等，并**去除 NUL 字节**。

    背景：部分 .txt 为 UTF-16（字节间夹 `\x00`），按 UTF-8 解码会残留 NUL；
    PostgreSQL 的 UTF-8 不接受 NUL（`CharacterNotInRepertoireError`），
    会直接导致分块入库 500。这里做编码探测 + NUL 清洗。
    """
    if not content:
        return ""
    maybe_utf16 = content.startswith((b"\xff\xfe", b"\xfe\xff")) or content.count(0) > max(
        1, len(content) // 10
    )
    if maybe_utf16:
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                return content.decode(enc).replace("\x00", "")
            except (UnicodeDecodeError, LookupError):
                continue
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(enc).replace("\x00", "")
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace").replace("\x00", "")


# 解析器注册表：source_type -> parser 实例
_PARSERS: dict[str, DocumentParser] = {}


def register_parser(parser: DocumentParser) -> None:
    _PARSERS[parser.source_type] = parser


def get_parser(source_type: str) -> DocumentParser | None:
    return _PARSERS.get(source_type)


def available_types() -> list[str]:
    return list(_PARSERS.keys())
