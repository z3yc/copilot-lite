"""Markdown 解析器：按标题层级切分章节。

规则：
- `#`~`######` 标题作为章节边界，形成层级；
- 标题前的连续正文归入前一个章节；文档开头无标题的正文作为 level=0 章节；
- 保留代码块与列表（不解析为 HTML，正文原样保留供检索）。
"""

import re

from app.rag.parsers.base import DocumentParser, ParsedDocument, Section, register_parser

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MarkdownParser(DocumentParser):
    source_type = "md"

    def parse(self, content: bytes, meta: dict | None = None) -> ParsedDocument:
        text = content.decode("utf-8", errors="replace")
        meta = meta or {}

        sections: list[Section] = []
        current_heading: str | None = None
        current_level = 0
        buffer: list[str] = []

        def flush() -> None:
            body = "\n".join(buffer).strip()
            if body or current_heading is not None:
                sections.append(
                    Section(heading=current_heading, level=current_level, content=body)
                )
            buffer.clear()

        for line in text.splitlines():
            m = _HEADING_RE.match(line.strip())
            if m:
                flush()
                current_heading = m.group(2).strip()
                current_level = len(m.group(1))
            else:
                buffer.append(line)

        flush()

        # 无任何章节时，整体作为一段（避免空文档）
        if not sections and text.strip():
            sections.append(Section(heading=None, level=0, content=text.strip()))

        title = meta.get("title") or (sections[0].heading if sections else "未命名文档")
        return ParsedDocument(title=title, source_type=self.source_type, sections=sections, meta=meta)


register_parser(MarkdownParser())
