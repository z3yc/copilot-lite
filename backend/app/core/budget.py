"""LLM 成本预算：每用户每日 token 上限（内存实现，多实例部署换 Redis）。

计量来源：app.core.llm 的进程级 usage 统计（_usage_stats）。
开启（LLM_DAILY_TOKEN_BUDGET > 0）后，超限的对话/解析请求返回 429。
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

# user_id -> {"date": "YYYY-MM-DD", "tokens": int}
_daily_usage: dict[str, dict[str, int]] = {}


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def check_token_budget(user_id) -> None:
    """超过每用户每日预算时抛 429；预算 ≤ 0 表示不限（仅统计）。"""
    budget = settings.LLM_DAILY_TOKEN_BUDGET
    if budget <= 0:
        return
    entry = _daily_usage.get(str(user_id))
    if entry and entry["date"] == _today() and entry["tokens"] >= budget:
        raise HTTPException(status_code=429, detail="今日模型用量已达上限，请明天再试")


def add_token_usage(user_id, tokens: int) -> None:
    """累计某用户今日用量（跨天自动清零重计）。"""
    if tokens <= 0:
        return
    key = str(user_id)
    entry = _daily_usage.get(key)
    if not entry or entry["date"] != _today():
        entry = {"date": _today(), "tokens": 0}
        _daily_usage[key] = entry
    entry["tokens"] += tokens
    logger.info("用户 %s 今日累计 %d tokens（预算 %d）", key[:8], entry["tokens"], settings.LLM_DAILY_TOKEN_BUDGET)


def reset_daily_usage() -> None:
    """测试用：清空内存计数。"""
    _daily_usage.clear()
