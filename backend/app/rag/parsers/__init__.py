"""解析器包：导入全部解析器以完成注册。"""

from app.rag.parsers import (  # noqa: F401
    code_parser,
    docx_parser,
    markdown_parser,
    pdf_parser,
    web_parser,
    wiki_parser,
)
from app.rag.parsers.base import (
    DocumentParser,
    ParsedDocument,
    Section,
    available_types,
    get_parser,
    register_parser,
)

__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "Section",
    "available_types",
    "get_parser",
    "register_parser",
]
