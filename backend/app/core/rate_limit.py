"""通用滑动窗口限流（内存实现；多实例/云端部署换 Redis）。

用途：保护昂贵接口（对话 / AI 解析）——登录限流已有独立实现（auth.py），
本模块面向 chat 等按用户维度限频的接口。
"""

import logging
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class SlidingWindowLimiter:
    """按 key 维度的滑动窗口限流器。

    窗口内请求时间戳存于 deque；每次检查先清理窗口外的旧记录，
    再判断当前窗口内是否已达上限。O(窗口内请求数)，个人量级足够。
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._stamps: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """记录本次请求；窗口内已达上限返回 False（拒绝）。"""
        now = time.monotonic()
        stamps = self._stamps[key]
        while stamps and now - stamps[0] > self.window_seconds:
            stamps.popleft()
        if len(stamps) >= self.max_requests:
            return False
        stamps.append(now)
        return True

    def reset(self) -> None:
        """测试用：清空全部计数。"""
        self._stamps.clear()
