"""统一日志配置：注入 request_id / user_id 上下文。

日志格式含 `[request_id]`，便于把一次请求的 API → Service → LLM → 工具
全链路日志串起来（对齐 AGENTS.md §15）。
"""

import logging
import sys

from app.core.context import get_request_id, get_user_id

_FORMAT = "%(asctime)s | %(levelname)-8s | [%(request_id)s] | %(name)s | %(message)s"


class ContextFilter(logging.Filter):
    """把当前请求上下文注入 LogRecord（缺失时展示 "-"）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.user_id = get_user_id()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
