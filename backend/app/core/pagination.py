"""列表分页（AGENTS.md §14：page/page_size，默认 20，最大 100）。"""

from pydantic import BaseModel

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PageOut[T](BaseModel):
    """分页响应体（作为统一响应结构的 data）。"""

    items: list[T]
    total: int
    page: int
    page_size: int


def normalize_page(page: int, page_size: int) -> tuple[int, int]:
    """约束页码与页大小（page≥1；1≤page_size≤100）。"""
    safe_page = max(1, page)
    safe_size = max(1, min(MAX_PAGE_SIZE, page_size))
    return safe_page, safe_size


def page_offset(page: int, page_size: int) -> tuple[int, int]:
    """返回 (offset, limit)。"""
    safe_page, safe_size = normalize_page(page, page_size)
    return (safe_page - 1) * safe_size, safe_size
