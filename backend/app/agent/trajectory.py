"""Agent 轨迹（trajectory）记录：让「路由 → 节点 → 工具 → 结果」可回放。

设计（Q0.7：多智能体不可观测 = 不可调试 / 不可评测）：
- 两个引擎产出**同形状**轨迹（同一 step 词汇表），前端与落库契约不随引擎分叉；
- 落库前**规范化**：步数上限、单步参数/结果截断、总字节上限，超限置 `truncated`；
- **禁落密钥**（AGENTS §6/§15 红线）：工具参数**与工具结果**均按 key 脱敏
  （结果回显 JSON 里的 token/password 同样是泄露面）；
- 可开关（AGENTS §8）：`AGENT_TRACE_ENABLED=false` 时零开销早退，`build()` 返回 `{}`。

规范化只发生在这里：引擎只管记录，落库口径由本模块统一决定。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

# ---- 规范化上限（落库体积口径；超限置 truncated=true）----
TRAJECTORY_MAX_STEPS = 20
TRAJECTORY_ARG_MAX = 300
TRAJECTORY_RESULT_MAX = 500
TRAJECTORY_MAX_BYTES = 16 * 1024

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


def elapsed_ms(started: float) -> int:
    """自 `started`（perf_counter 读数）到现在的毫秒数（整数）。"""
    return int((time.perf_counter() - started) * 1000)


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


def _clip(text: Any, limit: int) -> str:
    s = "" if text is None else str(text)
    return s if len(s) <= limit else s[:limit]


class TrajectoryRecorder:
    """一次运行的轨迹记录器。

    引擎按请求新建实例，无跨请求共享，故无需加锁；
    `reset()` 供同一个实例被复用（测试/重试）时清空。
    """

    def __init__(self, engine: str, enabled: bool = True) -> None:
        self.engine = engine
        self.enabled = enabled
        self._steps: list[dict] = []
        self._truncated = False
        self._t0 = time.perf_counter()

    def reset(self) -> None:
        self._steps = []
        self._truncated = False
        self._t0 = time.perf_counter()

    # ---------- 记录（未启用时零开销早退）----------

    def route(self, route: str, source: str, ms: int) -> None:
        """路由决策。source: llm（模型判定）/ keyword（关键词兜底）。"""
        if self.enabled:
            self._steps.append(
                {"type": "route", "route": route, "source": source, "ms": int(ms)}
            )

    def node(self, name: str) -> None:
        """进入某个子 Agent 节点（结构信息，不带耗时——耗时不与工具步重叠）。"""
        if self.enabled:
            self._steps.append({"type": "node", "node": name})

    def tool(
        self,
        name: str,
        arguments: str,
        result: str,
        status: str = "ok",
        ms: int = 0,
    ) -> None:
        if not self.enabled:
            return
        self._steps.append(
            {
                "type": "tool",
                "name": name,
                "arguments": _clip(redact_json_text(arguments), TRAJECTORY_ARG_MAX),
                "result": _clip(redact_json_text(result), TRAJECTORY_RESULT_MAX),
                "status": status,
                "ms": int(ms),
            }
        )

    def answer(self, chars: int) -> None:
        if self.enabled:
            self._steps.append({"type": "answer", "chars": int(chars)})

    # ---------- 规范化输出 ----------

    def build(self) -> dict:
        """规范化后的轨迹；未启用或无步时返回 `{}`（上层据此不落库）。"""
        if not self.enabled or not self._steps:
            return {}
        steps = list(self._steps)
        if len(steps) > TRAJECTORY_MAX_STEPS:
            steps = steps[:TRAJECTORY_MAX_STEPS]
            self._truncated = True
        payload = {
            "engine": self.engine,
            "total_ms": elapsed_ms(self._t0),
            "truncated": self._truncated,
            "steps": steps,
        }
        # 总字节上限：整步丢弃到装得下为止（至少留一步，便于定位是哪一轮）
        while (
            len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            > TRAJECTORY_MAX_BYTES
            and len(payload["steps"]) > 1
        ):
            payload["steps"] = payload["steps"][:-1]
            payload["truncated"] = True
        return payload
