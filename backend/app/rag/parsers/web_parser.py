"""网页解析器：提取正文并保留标题结构。

简化策略：解析 HTML 的 h1-h6 与段落，剔除脚本/样式/导航等噪声。
"""

from app.rag.parsers.base import (
    DocumentParser,
    ParsedDocument,
    Section,
    decode_text,
    register_parser,
)


class WebParser(DocumentParser):
    source_type = "web"

    def parse(self, content: bytes, meta: dict | None = None) -> ParsedDocument:
        from bs4 import BeautifulSoup

        meta = meta or {}
        soup = BeautifulSoup(decode_text(content), "html.parser")

        # 移除噪声节点
        for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
            tag.decompose()

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

        for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre"]):
            if el.name.startswith("h"):
                flush()
                current_heading = el.get_text(strip=True)
                current_level = int(el.name[1])
            else:
                text = el.get_text(strip=True)
                if text:
                    buffer.append(text)

        flush()

        title = meta.get("title") or (soup.title.string.strip() if soup.title and soup.title.string else "未命名网页")
        return ParsedDocument(
            title=title, source_type=self.source_type, sections=sections, meta=meta
        )


register_parser(WebParser())
