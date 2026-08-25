"""代码仓库解析器：按文件切分，保留路径信息。

输入约定：content 为打包文件清单文本（或单个文件内容），
meta 提供 file_path；每个文件 = 一个 Section，标题为相对路径。
"""

from app.rag.parsers.base import DocumentParser, ParsedDocument, Section, register_parser

# 常见文本源码扩展名（其余视为二进制跳过）
_TEXT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c",
    ".cpp", ".h", ".hpp", ".cs", ".php", ".rb", ".sh", ".sql", ".html",
    ".css", ".json", ".yaml", ".yml", ".toml", ".ini", ".md", ".txt",
    ".vue", ".xml", ".proto",
}


class CodeParser(DocumentParser):
    source_type = "code"

    def parse(self, content: bytes, meta: dict | None = None) -> ParsedDocument:
        meta = meta or {}
        file_path = meta.get("file_path", "code")
        text = content.decode("utf-8", errors="replace")

        sections = [
            Section(heading=file_path, level=0, content=text, meta={"file_path": file_path})
        ]
        return ParsedDocument(
            title=meta.get("title") or file_path,
            source_type=self.source_type,
            sections=sections,
            meta=meta,
        )


register_parser(CodeParser())
