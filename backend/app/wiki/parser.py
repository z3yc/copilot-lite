"""Wiki 解析器：在 Markdown 解析基础上叠加 frontmatter / 双链 / 标签。

source_type = "wiki"，复用 MarkdownParser 的标题分块逻辑；
链接与标签存入 ParsedDocument.meta，供同步层写链接图。
"""

from app.rag.parsers.base import DocumentParser, ParsedDocument, register_parser
from app.rag.parsers.markdown_parser import MarkdownParser
from app.wiki.links import extract_frontmatter, extract_links, extract_tags


class WikiParser(DocumentParser):
    source_type = "wiki"

    def parse(self, content: bytes, meta: dict | None = None) -> ParsedDocument:
        meta = meta or {}
        text = content.decode("utf-8", errors="replace")
        front, body = extract_frontmatter(text)

        markdown = MarkdownParser().parse(body.encode("utf-8"), meta=meta)
        title = str(front.get("title") or markdown.title)

        front_tags = front.get("tags") or []
        if isinstance(front_tags, str):
            front_tags = [front_tags]
        tags = list(dict.fromkeys([*front_tags, *extract_tags(body)]))

        markdown.meta.update(
            {
                "wiki_space": meta.get("wiki_space"),
                "wiki_path": meta.get("wiki_path"),
                "wiki_title": title,
                "links": [
                    {"target": ref.target, "alias": ref.alias, "kind": ref.kind}
                    for ref in extract_links(body)
                ],
                "tags": tags,
            }
        )
        return ParsedDocument(
            title=title,
            source_type=self.source_type,
            sections=markdown.sections,
            meta=markdown.meta,
        )


register_parser(WikiParser())
