"""LLM 结构化输出容错解析：剥离 markdown 围栏、提取首个 JSON 值。

背景：模型常把 JSON 包在 ```json 围栏里，或在前后附加解释文字；直接
``json.loads`` 会失败（记忆提取此前还是静默丢弃）。本模块提供宽容解析，
失败时返回调用方指定的默认值，避免"模型格式抖动 = 数据丢失"。
"""

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _strip_fence(text: str) -> str:
    """剥离首个 markdown 代码围栏；无围栏则返回去空白文本。"""
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


def parse_json(text: str | None, default: Any = None) -> Any:
    """从模型输出中解析 JSON；失败返回 default（不抛异常）。"""
    raw = _strip_fence(text or "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    # 兜底：截取首个 {..} / [..]（前后有解释文字时）
    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                continue
    return default


def parse_json_object(text: str | None, default: dict | None = None) -> dict:
    """解析为 dict；类型不符返回 default（缺省空 dict）。"""
    value = parse_json(text)
    if isinstance(value, dict):
        return value
    return {} if default is None else default


def parse_json_array(text: str | None, default: list | None = None) -> list:
    """解析为 list；类型不符返回 default（缺省空 list）。"""
    value = parse_json(text)
    if isinstance(value, list):
        return value
    return [] if default is None else default
