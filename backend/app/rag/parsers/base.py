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


# 解析器注册表：source_type -> parser 实例
_PARSERS: dict[str, DocumentParser] = {}


def register_parser(parser: DocumentParser) -> None:
    _PARSERS[parser.source_type] = parser


def get_parser(source_type: str) -> DocumentParser | None:
    return _PARSERS.get(source_type)


def available_types() -> list[str]:
    return list(_PARSERS.keys())
