"""解析器与分块测试。"""


from app.rag.chunking import chunk_document
from app.rag.parsers import get_parser

_MD_SAMPLE = """# 项目简介

这是一个 AI 助理项目。

## 技术栈

- FastAPI
- DeepSeek

## 架构

分为前端与后端。
"""


def test_markdown_parser_sections() -> None:
    """Markdown 按标题层级切分。"""
    parsed = get_parser("md").parse(_MD_SAMPLE.encode())
    assert parsed.title == "项目简介"
    headings = [s.heading for s in parsed.sections]
    assert headings == ["项目简介", "技术栈", "架构"]
    assert "FastAPI" in parsed.sections[1].content


def test_markdown_parser_plain_text() -> None:
    """无标题的纯文本整体成段。"""
    parsed = get_parser("md").parse("这是没有标题的笔记内容，仅此而已。".encode())
    assert len(parsed.sections) == 1
    assert parsed.sections[0].heading is None


def test_chunking_heading_path() -> None:
    """分块携带完整标题路径（溯源用）。"""
    content = """# 第一章

第一章内容。

## 第一节

第一节内容，用于检索测试。
"""
    parsed = get_parser("md").parse(content.encode())
    chunks = chunk_document(parsed)
    assert chunks
    # 含"第一节"的块应携带标题路径 ["第一章", "第一节"]
    target = next(c for c in chunks if "第一节内容" in c.content)
    assert target.meta["headings"] == ["第一章", "第一节"]


def test_chunking_long_text_split() -> None:
    """超长内容按段落切分为多块，且带重叠。"""
    long_body = "\n\n".join(f"这是第{i}段的内容，包含一些检索关键词。" for i in range(30))
    parsed = get_parser("md").parse(f"# 标题\n\n{long_body}".encode())
    chunks = chunk_document(parsed, max_size=100, overlap=20)
    assert len(chunks) > 1
    # 所有块都有 chunk_index 且连续
    indexes = [c.meta["chunk_index"] for c in chunks]
    assert indexes == list(range(len(chunks)))


def test_parser_registry() -> None:
    """五种解析器全部注册。"""
    types = sorted(get_parser(t) is not None for t in ["md", "pdf", "docx", "code", "web"])
    assert all(types)
