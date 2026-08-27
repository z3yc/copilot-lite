"""智能分块：把解析后的章节切分为检索单元。

策略（面试可讲）：
1. **标题层级锚定**：维护标题路径栈，块元数据携带完整标题链
   （如 ["第一章", "第一节"]），检索时可溯源、可过滤；
2. **段落聚合**：短章节整体成块；长章节按段落聚合到 max_size，
   相邻块保留 overlap 重叠字符，避免切断语义；
3. **块级元数据**：标题路径 / 页码 / 来源类型 / 文档内序号。
"""

from dataclasses import dataclass, field

from app.rag.parsers.base import ParsedDocument

DEFAULT_MAX_SIZE = 800  # 单块最大字符数
DEFAULT_OVERLAP = 100  # 相邻块重叠字符数


@dataclass
class ChunkData:
    """一次分块的产物（尚未入库）。"""

    content: str
    meta: dict = field(default_factory=dict)


def _split_long_text(text: str, max_size: int, overlap: int) -> list[str]:
    """按段落聚合切分长文本，相邻块保留 overlap 字符重叠（含聚合边界）。"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pure: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
            continue
        if len(current) + len(para) + 2 <= max_size:
            current = f"{current}\n\n{para}"
            continue
        pure.append(current)
        # 超长段落自身先切（滑动窗口，片间自重叠）
        while len(para) > max_size:
            pure.append(para[:max_size])
            para = para[max_size - overlap :]
        current = para
    if current:
        pure.append(current)

    # 块边界重叠统一注入：每块头部携带上一块结尾 overlap 字符。
    # 修复此前"多段聚合溢出边界零重叠"的问题（原实现仅超长单段落有重叠）。
    blocks: list[str] = []
    for i, block in enumerate(pure):
        if i > 0 and overlap > 0:
            block = f"{pure[i - 1][-overlap:]}\n\n{block}"
        blocks.append(block)
    return blocks


def chunk_document(
    parsed: ParsedDocument, max_size: int = DEFAULT_MAX_SIZE, overlap: int = DEFAULT_OVERLAP
) -> list[ChunkData]:
    """将解析结果分块，返回带元数据的 ChunkData 列表。"""
    chunks: list[ChunkData] = []
    heading_stack: list[str] = []  # 标题路径栈（按 level 维护）

    for section in parsed.sections:
        # 更新标题路径：level 对应层级（level=0 表示无标题）
        if section.heading and section.level > 0:
            heading_stack = heading_stack[: section.level - 1] + [section.heading]

        if not section.content:
            continue

        if len(section.content) <= max_size:
            chunks.append(
                ChunkData(
                    content=section.content,
                    meta={
                        "headings": list(heading_stack),
                        "page": section.page,
                        "source_type": parsed.source_type,
                    },
                )
            )
        else:
            for block in _split_long_text(section.content, max_size, overlap):
                chunks.append(
                    ChunkData(
                        content=block,
                        meta={
                            "headings": list(heading_stack),
                            "page": section.page,
                            "source_type": parsed.source_type,
                        },
                    )
                )

    # 文档内序号（供引用溯源展示）
    for i, chunk in enumerate(chunks):
        chunk.meta["chunk_index"] = i
    return chunks
