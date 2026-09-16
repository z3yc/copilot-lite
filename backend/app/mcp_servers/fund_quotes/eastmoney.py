"""东方财富公开行情数据源（只读、无 Key）。

- 只取结构化字段：`FSRQ`(净值日期) / `DWJZ`(单位净值) / `JZZZL`(净值增长率%)，
  以及相邻上一期的 `DWJZ` 作为 `prev_nav`（F3 算当日盈亏用）；
- 本层只做**最小解析**（空串/None/非数字 → None），**范围校验留给客户端适配器**
  （AGENTS §6.6：外部数据一律不可信，校验单点放在适配层）；
- 任何失败（超时/HTTP 错误/非 JSON）返回 None 并 WARNING：由上层如实标注「未取到」，
  **不抛穿、不编造**（设计 §8）。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

LSJZ_URL = "https://api.fund.eastmoney.com/f10/lsjz"
# 东财接口要求带 Referer，否则返回空数据/404
_HEADERS = {"Referer": "https://fundf10.eastmoney.com/", "User-Agent": "copilot-lite/0.1"}
_TIMEOUT_SECONDS = 8.0


class QuoteProvider(Protocol):
    """行情数据源协议（server 只依赖它，便于注入 Fake 与将来换源）。"""

    async def fetch_nav(self, code: str) -> dict[str, Any] | None: ...


def _num(value: Any) -> float | None:
    """宽松转数字：空串/None/非数字 → None。"""
    if value is None:
        return None
    try:
        text = str(value).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


class EastmoneyProvider:
    """东方财富 `f10/lsjz`：取最近两期净值（当期 + 上一期）。"""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_nav(self, code: str) -> dict[str, Any] | None:
        params = {"fundCode": code, "pageIndex": 1, "pageSize": 2}
        try:
            if self._client is not None:
                resp = await self._client.get(LSJZ_URL, params=params, headers=_HEADERS)
            else:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    resp = await client.get(LSJZ_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            logger.warning("行情取数失败: code=%s", code, exc_info=True)
            return None

        rows = ((payload or {}).get("Data") or {}).get("LSJZList") or []
        if not rows:
            return None
        latest = rows[0]
        previous = rows[1] if len(rows) > 1 else {}
        return {
            "code": code,
            "nav": _num(latest.get("DWJZ")),
            "nav_date": latest.get("FSRQ"),
            "prev_nav": _num(previous.get("DWJZ")) if previous else None,
            "change_pct": _num(latest.get("JZZZL")),
        }
