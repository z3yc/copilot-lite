"""PDF 解析器：按页提取文本，携带页码元数据。

简化策略（个人知识库场景够用）：
- 每页作为独立 Section（page 记录页码），保留页码供引用溯源；
- 标题层级置 0（不尝试识别 PDF 标题树，避免依赖复杂布局分析）。
"""

from io import BytesIO

from app.rag.parsers.base import DocumentParser, ParsedDocument, Section, register_parser


class PdfParser(DocumentParser):
    source_type = "pdf"

    def parse(self, content: bytes, meta: dict | None = None) -> ParsedDocument:
        from pypdf import PdfReader

        meta = meta or {}
        reader = PdfReader(BytesIO(content))
        sections: list[Section] = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                sections.append(Section(heading=None, level=0, content=text, page=i))

        title = meta.get("title") or reader.metadata.title or "未命名PDF"
        return ParsedDocument(
            title=title, source_type=self.source_type, sections=sections, meta=meta
        )


register_parser(PdfParser())
