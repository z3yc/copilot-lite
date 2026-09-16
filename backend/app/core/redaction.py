"""敏感值脱敏：日志/轨迹/错误信息统一入口（AGENTS §6.1/§15）。

放在 `core` 而非 `agent`：infra 层（如 `app/mcp` 的 server `env` 回显、
MCP 错误文本）也要脱敏，而 infra **不得反向 import agent**（AGENTS §12 依赖方向）。
`app/agent/trajectory.py` 保留 re-export，旧 import 路径继续可用。
"""

from __future__ import annotations

import json
import re
from typing import Any

# 敏感 key（密钥类）：命中即把值替换为掩码。
# 前置 lookbehind 故意不写：它会让 accessToken / clientSecret / myApiKey
# 这类驼峰（或带前缀）key 从词中间起匹配失败，从而整条漏网。
# 尾随断言用 (?-i:...) 局部关闭 IGNORECASE，使 `[a-z0-9]` 只匹配小写字母/数字：
# 于是 `max_tokens` / `tokens_total`（`token` 后跟小写 `s`）仍不误伤，
# 而 `secretKey` / `secretValue` 这类驼峰续词（后跟大写字母）能正确命中。
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|secret|token|password|passwd|credential|authorization)"
    r"(?-i:(?![a-z0-9]))",
    re.IGNORECASE,
)
_MASK = "***"


def redact(value: Any) -> Any:
    """递归把敏感 key 的值替换为掩码（dict/list 深入；其余原样返回）。"""
    if isinstance(value, dict):
        return {
            k: (_MASK if _SENSITIVE_KEY_RE.search(str(k)) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def redact_json_text(text: str) -> str:
    """工具参数**与工具结果**（均为 JSON 字符串）脱敏。

    解析成功且确有敏感 key 时才改写（避免无谓地改变原始格式）；
    解析失败（非 JSON 文本）则原样返回——不猜测、不改写自由文本，
    非法 JSON 由上层工具层兜底处理，不在此报错。
    """
    if not text:
        return text
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return text
    redacted = redact(parsed)
    if redacted == parsed:
        return text
    return json.dumps(redacted, ensure_ascii=False)
