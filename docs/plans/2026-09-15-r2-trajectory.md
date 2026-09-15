# R2 · Q1 trajectory（回答轨迹落库 + 前端可见）实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让每次 Agent 回答的「路由 → 节点 → 工具 → 结果 → 耗时」全量落进 `Message.extra.trajectory`，并在前端消息气泡内以可展开面板可见，由 `AGENT_TRACE_ENABLED` 开关控制。

**Architecture:** 新增 `app/agent/trajectory.py`（`TrajectoryRecorder`：记录 → 规范化 → 截断/脱敏）作为唯一轨迹来源；两个引擎（LangGraph 主干 / 手写 `Orchestrator` 对照）产出**同一 step 词汇表**的轨迹，挂在 `agent.last_trajectory`；`chat.py` 沿用既有 `extra` 组装路径落库，并在 SSE `done` 事件 data 中**增量**附带 `trajectory`；前端新增 `TrajectoryPanel` 组件并在 `ChatPanel` 消息气泡内渲染。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy(async) / LangGraph / langchain-core；React 18 + TS + Ant Design + vitest。

---

## Global Constraints

> 每个任务的实现者与评审者都必须遵守；评审者按此逐条核对。

1. **工作目录**：主仓库 `C:/Users/asus/Documents/copilot-lite`（分支 `feat/agent-trajectory`，基线提交 `06ab3bb`）。私有文档在 `C:/Users/asus/Documents/copilot-lite-private`（`private-docs` 分支）。
2. **控制台是 GBK**：核对中文一律 `python -c "print(ascii(open(...).read()))"`，不要靠肉眼读终端输出。
3. **提交规范**（AGENTS §3）：Conventional Commits，描述用中文。一个提交只解决一个问题。
4. **轨迹契约（精确，前端与两个引擎都依赖）**：

   ```jsonc
   {
     "engine": "langgraph" | "handwritten",
     "total_ms": 3120,        // 整轮墙钟耗时（毫秒，整数）
     "truncated": false,      // 是否有任何步被丢弃/截断
     "steps": [ /* 见下 */ ]
   }
   ```
   - `{"type": "route", "route": "kb"|"tools"|"chat", "source": "llm"|"keyword", "ms": 812}`
   - `{"type": "node", "node": "kb_agent"|"tools_agent"|"chat_agent"|"orchestrator"}`
   - `{"type": "tool", "name": str, "arguments": str, "result": str, "status": "ok"|"pending_confirmation", "ms": int}`
   - `{"type": "answer", "chars": 210}`
   - **手写引擎没有路由能力，因此不产 `route` step**——这是契约允许的，不是缺陷。
5. **规范化上限（落库体积口径，常量值必须精确）**：
   `TRAJECTORY_MAX_STEPS = 20`、`TRAJECTORY_ARG_MAX = 300`、`TRAJECTORY_RESULT_MAX = 500`、`TRAJECTORY_MAX_BYTES = 16 * 1024`。
6. **禁落密钥**（AGENTS §6/§15 硬红线）：轨迹中任何敏感 key（`api_key` / `secret` / `token` / `password` / `credential` / `authorization`）的**值**一律替换为 `***`；`max_tokens` 这类含 `token` 字样的普通 key **不得**被误伤。
7. **配置三件套**（AGENTS §7）：`AGENT_TRACE_ENABLED: bool = True` 必须同时出现在 `backend/app/core/config.py`、`deploy/.env.example`（激活值）、`backend/.env.example`（注释值），并在 `backend/tests/conftest.py` 默认关闭。
8. **SSE 契约**：不新增事件类型、不删除/改名既有事件；只在 `done` 事件的 `data` 中**增补**可选 `trajectory` 字段（旧前端忽略即可）。
9. **不做**（已冻结，见 `OPTIMIZATION_PLAN.md` §11）：实时逐事件推送、Task 实体、工具白名单与渐进披露、supervisor 路由逻辑改造、引用来源扩字段（R3）。
10. **前端安全**：轨迹里的 `arguments` / `result` 是模型与外部数据，**只能**用 React 默认转义渲染；禁止对它们使用 `dangerouslySetInnerHTML`（AGENTS §5）。
11. **每批验收门槛**（AGENTS §8/§20）：后端 `pytest` 全绿 + 覆盖率 ≥80% + `ruff check .` 全过；前端 `npm test` + `npm run build` 零错误；修复/新功能带防回归测试。
12. **基线（本计划开工前实测）**：后端 **343 passed / 覆盖率 82.53%**、`ruff` 全过；前端 **92 passed / 18 files**、`build` 零错误。

---

## Task 1: `TrajectoryRecorder` + `AGENT_TRACE_ENABLED` 配置三件套

**Files:**
- Create: `backend/app/agent/trajectory.py`
- Modify: `backend/app/core/config.py`（`# Agent 循环参数` 组，`AGENT_ENGINE` 之后）
- Modify: `deploy/.env.example`（`# ---- Agent 引擎 ----` 段）
- Modify: `backend/.env.example`（新增 `# ---- Agent 轨迹 ----` 段）
- Modify: `backend/tests/conftest.py`（开关默认关那一段）
- Test: `backend/tests/test_trajectory.py`

**Step 1: 配置三件套（先提交这一笔）**

`backend/app/core/config.py`，在 `AGENT_ENGINE: str = "langgraph"` 之后加：

```python
    # Agent 轨迹（trajectory）落库开关：记录 路由/节点/工具/结果 到 Message.extra
    # （可观测性；关闭时轨迹为空 dict，前端不显示轨迹面板）
    AGENT_TRACE_ENABLED: bool = True
```

`deploy/.env.example`，在 `AGENT_ENGINE=langgraph` 之后加：

```
# Agent 轨迹落库开关（可观测：路由 / 节点 / 工具 / 结果 / 耗时）
AGENT_TRACE_ENABLED=true
```

`backend/.env.example`，在 `# ---- Wiki 本地知识库（Obsidian 导入）----` 段之前加：

```
# ---- Agent 轨迹（可观测）----
# AGENT_TRACE_ENABLED=true         # 轨迹落 Message.extra（关闭则前端不显示轨迹面板）
```

`backend/tests/conftest.py`，在 `os.environ["EMBEDDING_PREWARM"] = "false"` 之后加：

```python
# 测试环境默认关闭 Agent 轨迹（需要轨迹的用例自行 monkeypatch 打开）
os.environ["AGENT_TRACE_ENABLED"] = "false"
```

验证：`.venv\Scripts\python.exe -c "from app.core.config import Settings; print(Settings().AGENT_TRACE_ENABLED)"` → `False`（conftest 未加载时不生效；此处直接跑会打印 `True`，都算通过——以 `tests` 下断言为准）。

提交：`chore(config): 新增 AGENT_TRACE_ENABLED 三件套——轨迹可观测开关，测试环境默认关`

**Step 2: 写失败测试**

创建 `backend/tests/test_trajectory.py`：

```python
"""trajectory 记录器测试：步序、规范化上限、脱敏、开关。"""

import json

from app.agent.trajectory import (
    TRAJECTORY_ARG_MAX,
    TRAJECTORY_MAX_BYTES,
    TRAJECTORY_MAX_STEPS,
    TRAJECTORY_RESULT_MAX,
    TrajectoryRecorder,
    redact_json_args,
)


def test_disabled_recorder_returns_empty() -> None:
    """关闭开关：不记录，build() 返回空 dict（前端据此不显示面板）。"""
    rec = TrajectoryRecorder("langgraph", enabled=False)
    rec.route("kb", "llm", 10)
    rec.node("kb_agent")
    rec.tool("kb_search", '{"query": "x"}', "结果")
    rec.answer(3)
    assert rec.build() == {}


def test_records_steps_in_order() -> None:
    rec = TrajectoryRecorder("langgraph")
    rec.route("tools", "llm", 12)
    rec.node("tools_agent")
    rec.tool("kb_search", '{"query": "x"}', "结果A", ms=7)
    rec.answer(9)

    built = rec.build()
    assert built["engine"] == "langgraph"
    assert built["truncated"] is False
    assert built["total_ms"] >= 0
    assert [s["type"] for s in built["steps"]] == ["route", "node", "tool", "answer"]
    assert built["steps"][0] == {"type": "route", "route": "tools", "source": "llm", "ms": 12}
    tool = built["steps"][2]
    assert tool["name"] == "kb_search"
    assert tool["status"] == "ok"
    assert tool["ms"] == 7
    assert tool["result"] == "结果A"


def test_steps_capped_and_marked_truncated() -> None:
    rec = TrajectoryRecorder("langgraph")
    for i in range(TRAJECTORY_MAX_STEPS + 5):
        rec.tool(f"t{i}", "{}", "r")
    built = rec.build()
    assert len(built["steps"]) == TRAJECTORY_MAX_STEPS
    assert built["truncated"] is True


def test_arg_and_result_clipped() -> None:
    rec = TrajectoryRecorder("langgraph")
    rec.tool("t", json.dumps({"q": "长" * 1000}, ensure_ascii=False), "结" * 2000)
    step = rec.build()["steps"][0]
    assert len(step["arguments"]) == TRAJECTORY_ARG_MAX
    assert len(step["result"]) == TRAJECTORY_RESULT_MAX


def test_sensitive_keys_are_masked() -> None:
    """密钥不入轨迹（AGENTS §6/§15 硬红线）。"""
    rec = TrajectoryRecorder("langgraph")
    rec.tool("t", '{"api_key": "sk-secret-123", "query": "ok"}', "r")
    args = rec.build()["steps"][0]["arguments"]
    assert "sk-secret-123" not in args
    assert "***" in args
    assert "ok" in args


def test_redact_json_args_keeps_non_sensitive_untouched() -> None:
    """无敏感 key 时原样返回（不改写格式）。"""
    raw = '{ "query" : "x" }'
    assert redact_json_args(raw) == raw


def test_redact_does_not_touch_token_lookalike() -> None:
    """max_tokens 不是密钥（防误伤）；refresh_token 是。"""
    out = redact_json_args('{"max_tokens": 128, "refresh_token": "abc"}')
    assert '"max_tokens": 128' in out
    assert "abc" not in out


def test_total_bytes_capped() -> None:
    """总字节上限：整步丢弃到装得下为止。"""
    rec = TrajectoryRecorder("langgraph")
    for i in range(TRAJECTORY_MAX_STEPS):
        rec.tool(f"tool-{i}", "{}", "结" * TRAJECTORY_RESULT_MAX)
    built = rec.build()
    size = len(json.dumps(built, ensure_ascii=False).encode("utf-8"))
    assert size <= TRAJECTORY_MAX_BYTES
    assert built["truncated"] is True


def test_reset_clears_steps() -> None:
    rec = TrajectoryRecorder("langgraph")
    rec.node("kb_agent")
    rec.reset()
    assert rec.build() == {}
```

**Step 3: 跑测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_trajectory.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.agent.trajectory'`

**Step 4: 实现 `backend/app/agent/trajectory.py`**

```python
"""Agent 轨迹（trajectory）记录：让「路由 → 节点 → 工具 → 结果」可回放。

设计（Q0.7：多智能体不可观测 = 不可调试 / 不可评测）：
- 两个引擎产出**同形状**轨迹（同一 step 词汇表），前端与落库契约不随引擎分叉；
- 落库前**规范化**：步数上限、单步参数/结果截断、总字节上限，超限置 `truncated`；
- **禁落密钥**（AGENTS §6/§15 红线）：工具参数按 key 脱敏，结果按截断口径；
- 可开关（AGENTS §8）：`AGENT_TRACE_ENABLED=false` 时零开销早退，`build()` 返回 `{}`。

规范化只发生在这里：引擎只管记录，落库口径由本模块统一决定。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---- 规范化上限（落库体积口径；超限置 truncated=true）----
TRAJECTORY_MAX_STEPS = 20
TRAJECTORY_ARG_MAX = 300
TRAJECTORY_RESULT_MAX = 500
TRAJECTORY_MAX_BYTES = 16 * 1024

# 敏感 key（密钥类）：命中即把值替换为掩码。用前后视断言避免误伤
# `max_tokens`（`token` 后跟 `s`）、`tokens_total` 这类普通字段。
_SENSITIVE_KEY_RE = re.compile(
    r"(?<![a-z0-9])"
    r"(api[_-]?key|apikey|secret|token|password|passwd|credential|authorization)"
    r"(?![a-z0-9])",
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


def redact_json_args(arguments: str) -> str:
    """工具参数（JSON 字符串）脱敏。

    解析成功且确有敏感 key 时才改写（避免无谓地改变原始格式）；
    解析失败则原样返回（非法 JSON 由上层工具层兜底处理，不在此报错）。
    """
    if not arguments:
        return arguments
    try:
        parsed = json.loads(arguments)
    except (ValueError, TypeError):
        return arguments
    redacted = redact(parsed)
    if redacted == parsed:
        return arguments
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
                "arguments": _clip(redact_json_args(arguments), TRAJECTORY_ARG_MAX),
                "result": _clip(result, TRAJECTORY_RESULT_MAX),
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
```

**Step 5: 跑测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_trajectory.py -q`
Expected: `9 passed`

**Step 6: lint + 提交**

```bash
.venv\Scripts\ruff.exe check .
git add backend/app/agent/trajectory.py backend/tests/test_trajectory.py
git commit -m "feat(agent): 新增 TrajectoryRecorder——统一轨迹记录与规范化（上限/截断/脱敏）"
```

---

## Task 2: LangGraph 引擎接线（route / node / tool / answer + 耗时）

**Files:**
- Modify: `backend/app/agent/langgraph_engine.py`
- Modify: `backend/app/agent/base.py`（`BaseAgent` 文档补 `last_trajectory` 契约）
- Test: `backend/tests/test_langgraph_engine.py`

**Step 1: 写失败测试**

追加到 `backend/tests/test_langgraph_engine.py`（文件顶部需补 `import time`、`from app.core.config import settings` 已有、`from app.agent.trajectory import TRAJECTORY_RESULT_MAX`）：

```python
# ---------- 轨迹（trajectory） ----------


def _enable_trace(monkeypatch) -> None:
    """conftest 默认关闭轨迹，需要轨迹的用例自行打开（顺带证明开关生效）。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", True)


@pytest.mark.asyncio
async def test_trajectory_records_route_node_and_answer(monkeypatch, db_session) -> None:
    """路由 → 节点 → 回复：可复原路由判定来源与选中的子 Agent。"""
    _enable_trace(monkeypatch)
    engine = make_engine([_route_msg("chat"), AIMessage(content="你好")])
    await engine.run(db_session, DEFAULT_USER_ID, [], "你好")

    traj = engine.last_trajectory
    assert traj["engine"] == "langgraph"
    assert traj["truncated"] is False
    assert [s["type"] for s in traj["steps"]] == ["route", "node", "answer"]
    route = traj["steps"][0]
    assert route["route"] == "chat"
    assert route["source"] == "llm"
    assert route["ms"] >= 0
    assert traj["steps"][1]["node"] == "chat_agent"
    assert traj["steps"][2]["chars"] == len("你好")


@pytest.mark.asyncio
async def test_trajectory_route_source_keyword_on_bad_llm_output(monkeypatch, db_session) -> None:
    """Supervisor 输出不可解析 → 关键词兜底，轨迹如实标注 source=keyword。"""
    _enable_trace(monkeypatch)
    engine = make_engine([AIMessage(content="我无法判断"), AIMessage(content="好的")])
    await engine.run(db_session, DEFAULT_USER_ID, [], "我的笔记里有什么")

    route = engine.last_trajectory["steps"][0]
    assert route["route"] == "kb"
    assert route["source"] == "keyword"


@pytest.mark.asyncio
async def test_trajectory_records_tool_step(monkeypatch, db_session) -> None:
    """工具调用与结果进轨迹（含耗时与状态）。"""
    _enable_trace(monkeypatch)
    engine = make_engine(
        [
            _route_msg("tools"),
            AIMessage(content="", tool_calls=[{"name": "kb_search", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="完成"),
        ]
    )
    await engine.run(db_session, DEFAULT_USER_ID, [], "检索一下")

    steps = engine.last_trajectory["steps"]
    tool = next(s for s in steps if s["type"] == "tool")
    assert tool["name"] == "kb_search"
    assert tool["status"] == "ok"
    assert tool["arguments"] == '{"query": "x"}'
    assert tool["ms"] >= 0
    assert tool["result"]


@pytest.mark.asyncio
async def test_trajectory_disabled_returns_empty(monkeypatch, db_session) -> None:
    """开关关闭：不记录（AGENTS §8）。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", False)
    engine = make_engine([_route_msg("chat"), AIMessage(content="你好")])
    await engine.run(db_session, DEFAULT_USER_ID, [], "你好")
    assert engine.last_trajectory == {}


@pytest.mark.asyncio
async def test_trajectory_no_secret_leak(monkeypatch, db_session) -> None:
    """轨迹禁落密钥（AGENTS §6/§15 硬红线）。"""
    _enable_trace(monkeypatch)
    engine = make_engine(
        [
            _route_msg("tools"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "kb_search", "args": {"query": "x", "api_key": "sk-leak-me"}, "id": "c1"}
                ],
            ),
            AIMessage(content="完成"),
        ]
    )
    await engine.run(db_session, DEFAULT_USER_ID, [], "检索一下")

    blob = json.dumps(engine.last_trajectory, ensure_ascii=False)
    assert "sk-leak-me" not in blob


@pytest.mark.asyncio
async def test_stream_records_trajectory(monkeypatch, db_session) -> None:
    """流式路径同样产出轨迹（回复长度=产出字符数）。"""
    _enable_trace(monkeypatch)
    engine = make_engine([_route_msg("chat"), AIMessage(content="流式回复")])
    parts = [chunk async for chunk in engine.run_stream(db_session, DEFAULT_USER_ID, [], "你好")]

    traj = engine.last_trajectory
    assert [s["type"] for s in traj["steps"]] == ["route", "node", "answer"]
    assert traj["steps"][2]["chars"] == len("".join(parts))
```

> 注：`FakeToolChatModel` 是 `GenericFakeChatModel`，`tool_calls` 需用 `AIMessage(..., tool_calls=[...])` 构造；若现有文件里已有构造工具调用的写法，**照抄现有写法**，不要新造一套。

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_langgraph_engine.py -q -k trajectory`
Expected: FAIL —— `AttributeError: 'LangGraphEngine' object has no attribute 'last_trajectory'`

**Step 3: 实现**

`backend/app/agent/langgraph_engine.py`：

1. 顶部补 `import time`，并加 `from app.agent.trajectory import TrajectoryRecorder, elapsed_ms`
2. `__init__` 末尾（`self.graph = ...` 之前）加：

```python
        # 本轮轨迹（route/node/tool/answer）：run 后由上层写入 Message.extra
        self.trace = TrajectoryRecorder("langgraph", enabled=settings.AGENT_TRACE_ENABLED)
        # 轨迹规范化结果（run/run_stream 收尾时写入；开关关闭时为空 dict）
        self.last_trajectory: dict = {}
```

3. `_make_supervisor` 的 `node`：改为记录耗时与来源：

```python
        async def node(state: AgentState) -> dict:
            # Supervisor 只做意图路由：仅带滚动窗口内的对话历史（不含 system 注入）
            _, convo = split_system_context(state["history"], settings.HISTORY_WINDOW)
            messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)]
            messages.extend(_to_langchain_messages(convo))
            messages.append(HumanMessage(content=state["user_message"]))
            started = time.perf_counter()
            route = ""
            source = "keyword"  # 兜底口径：只有模型给出合法路由才算 llm
            try:
                resp = await self.llm.ainvoke(messages)
                route = _parse_route(getattr(resp, "content", None) or "") or ""
                if route in ROUTES:
                    source = "llm"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supervisor 意图判断失败，走关键词兜底: %s", exc)
            if route not in ROUTES:
                route = _keyword_route(state["user_message"])
            self.trace.route(route, source, elapsed_ms(started))
            logger.info("路由: %s <- %s", route, state["user_message"][:20])
            return {"route": route}
```

4. `_make_agent` 的 `node`：开头记节点、工具处记工具步：

```python
        async def node(state: AgentState) -> dict:
            self.trace.node(node_name)
            # system 上下文（附件/记忆）常驻 + 对话历史滚动窗口（与手写引擎同策略）
```

工具循环内，把现有的两处 `json.dumps(args, ensure_ascii=False)` 提为一次计算，并记录轨迹：

```python
                for tc in resp.tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("args") or {}
                    logger.info("调用工具: %s(%s)", name, args)
                    args_json = json.dumps(args, ensure_ascii=False)
                    started = time.perf_counter()
                    if self.registry.is_confirmation_required(name):
                        self.pending_confirmation.append(
                            {
                                "name": name,
                                "arguments": args_json,
                                "tool_call_id": tc.get("id", ""),
                            }
                        )
                        result = "（该操作需用户确认，已挂起，尚未执行）"
                        self.trace.tool(
                            name, args_json, result,
                            status="pending_confirmation", ms=elapsed_ms(started),
                        )
                    else:
                        result = await self.registry.execute(name, args_json, self._ctx)
                        self.trace.tool(
                            name, args_json, str(result),
                            status="ok", ms=elapsed_ms(started),
                        )
                        self.last_tool_calls.append(
                            {
                                "name": name,
                                "arguments": args_json,
                                "result": str(result)[:500],
                            }
                        )
                    messages.append(ToolMessage(content=result, tool_call_id=tc.get("id", "")))
```

5. `run()`：开头 `self.trace.reset()`，结尾收尾：

```python
        self.trace.reset()
        ...
        result = await self.graph.ainvoke(state)
        self.last_citations = list(self._ctx.citations)
        reply = result.get("reply") or ""
        self.trace.answer(len(reply))
        self.last_trajectory = self.trace.build()
        return reply
```

6. `run_stream()`：开头 `self.trace.reset()`，累加产出字符数，在既有收尾处一并收尾：

```python
        self.trace.reset()
        ...
        leaf_nodes = ("kb_agent", "tools_agent", "chat_agent")
        yielded = False
        chars = 0
        async for event in self.graph.astream_events(state, version="v2"):
            ...
            if isinstance(content, str) and content:
                yielded = True
                chars += len(content)
                yield content
        if self._ctx is not None:
            self.last_citations = list(self._ctx.citations)
        # 挂起等确认的操作由引擎生成回复，不经过模型流，需单独产出
        if self.pending_confirmation and not yielded:
            text = confirmation_reply(self.pending_confirmation)
            chars += len(text)
            yield text
        self.trace.answer(chars)
        self.last_trajectory = self.trace.build()
```

7. `backend/app/agent/base.py`：在 `BaseAgent` 类 docstring 中补一段契约说明（不改签名）：

```
    可选属性（两个实现都提供，供上层落 Message.extra）：
    last_tool_calls / pending_confirmation / last_citations / last_trajectory
```

**Step 4: 跑测试**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_langgraph_engine.py tests/test_trajectory.py -q`
Expected: 全绿（`-k trajectory` 的 6 个用例全过，原有用例不回归）

**Step 5: 全量回归 + lint + 提交**

```bash
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
git add backend/app/agent/langgraph_engine.py backend/app/agent/base.py backend/tests/test_langgraph_engine.py
git commit -m "feat(agent): LangGraph 引擎产出轨迹——路由来源/节点/工具/耗时全量记录"
```

---

## Task 3: 手写 `Orchestrator` 接线（同形状轨迹）

**Files:**
- Modify: `backend/app/agent/orchestrator.py`
- Test: `backend/tests/test_orchestrator.py`

**背景**：手写引擎被冻结为对照/回退（Q0.2），但前端与落库契约不随引擎分叉，故它也产出轨迹。**它没有路由能力，因此不产 `route` step**（契约允许）。

**Step 1: 写失败测试**

追加到 `backend/tests/test_orchestrator.py`（照该文件既有 fake LLM 用法）：

```python
# ---------- 轨迹（trajectory） ----------


async def test_trajectory_records_node_and_answer(monkeypatch) -> None:
    """手写引擎：节点=orchestrator，无 route step（它没有路由能力）。"""
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", True)
    ...  # 照本文件既有 fake LLM 构造一次纯文本回复
    await agent.run(session=None, user_id="u1", history=[], user_message="你好")

    traj = agent.last_trajectory
    assert traj["engine"] == "handwritten"
    assert [s["type"] for s in traj["steps"]] == ["node", "answer"]
    assert traj["steps"][0]["node"] == "orchestrator"


async def test_trajectory_records_tool_step(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", True)
    ...  # fake LLM 先返回 tool_calls，再返回文本
    tool = next(s for s in agent.last_trajectory["steps"] if s["type"] == "tool")
    assert tool["name"] == "kb_search"
    assert tool["status"] == "ok"


async def test_trajectory_disabled_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AGENT_TRACE_ENABLED", False)
    ...  # 一次纯文本回复
    assert agent.last_trajectory == {}
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_orchestrator.py -q -k trajectory`
Expected: FAIL —— 无 `last_trajectory`

**Step 3: 实现**

1. 顶部补 `import time`，加 `from app.agent.trajectory import TrajectoryRecorder, elapsed_ms`
2. `__init__` 末尾加：

```python
        # 本轮轨迹（node/tool/answer）：run 后由上层写入 Message.extra
        self.trace = TrajectoryRecorder("handwritten", enabled=settings.AGENT_TRACE_ENABLED)
        # 轨迹规范化结果（run/run_stream 收尾时写入；开关关闭时为空 dict）
        self.last_trajectory: dict = {}
```

3. 加一个收尾私有方法（**每个出口都必须调用**，防漏记）：

```python
    def _seal_trajectory(self, chars: int) -> None:
        """轨迹收尾：记录回复长度并规范化（run/run_stream 的每个出口都要调用）。"""
        self.trace.answer(chars)
        self.last_trajectory = self.trace.build()

    def _start_trajectory(self) -> None:
        """轨迹开场：重置并记录节点（手写引擎只有一个执行节点，无路由）。"""
        self.trace.reset()
        self.trace.node("orchestrator")
```

4. `run()`：`self.last_citations = []` 之后加 `self._start_trajectory()`；三处出口改为先算 reply 再收尾：

```python
            if not result.has_tool_calls:
                self.last_citations = list(ctx.citations)
                reply = result.content or "（模型未返回内容）"
                self._seal_trajectory(len(reply))
                return reply
```
```python
            if self.pending_confirmation:
                self.last_citations = list(ctx.citations)
                reply = confirmation_reply(self.pending_confirmation)
                self._seal_trajectory(len(reply))
                return reply
```
```python
        self.last_citations = list(ctx.citations)
        reply = "（已达到最大工具调用轮数，请简化请求后重试）"
        self._seal_trajectory(len(reply))
        return reply
```

5. `run()` 的工具循环内加轨迹（参数直接用 `tc.arguments`；`status` 区分挂起）：

```python
            for tc in result.tool_calls:
                logger.info("调用工具: %s(%s)", tc.name, tc.arguments)
                started = time.perf_counter()
                if self.registry.is_confirmation_required(tc.name):
                    # 高风险副作用：不执行，挂起等用户确认
                    self.pending_confirmation.append(
                        {"name": tc.name, "arguments": tc.arguments, "tool_call_id": tc.id}
                    )
                    tool_result = "（该操作需用户确认，已挂起，尚未执行）"
                    self.trace.tool(
                        tc.name, tc.arguments, tool_result,
                        status="pending_confirmation", ms=elapsed_ms(started),
                    )
                else:
                    tool_result = await self.registry.execute(tc.name, tc.arguments, ctx)
                    self.trace.tool(
                        tc.name, tc.arguments, tool_result,
                        status="ok", ms=elapsed_ms(started),
                    )
                    self.last_tool_calls.append(
                        {
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": tool_result[:500],
                        }
                    )
```

6. `run_stream()`：同样在 `self.last_citations = []` 之后加 `self._start_trajectory()`；`chars = 0` 定义在 `for _ in range(self.max_turns):` 之前；`yield delta.content` 处累加；三处出口收尾：

```python
        chars = 0
        for _ in range(self.max_turns):
```
```python
                    if delta and delta.content:
                        chars += len(delta.content)
                        yield delta.content
```
```python
            if not tool_calls:
                self.last_citations = list(ctx.citations)
                self._seal_trajectory(chars)
                return  # 纯文本轮完成
```
```python
            if self.pending_confirmation:
                self.last_citations = list(ctx.citations)
                text = confirmation_reply(self.pending_confirmation)
                chars += len(text)
                self._seal_trajectory(chars)
                yield text
                return
```
```python
        self.last_citations = list(ctx.citations)
        text = "（已达到最大工具调用轮数，请简化请求后重试）"
        chars += len(text)
        self._seal_trajectory(chars)
        yield text
```

7. `run_stream()` 的工具循环（`for c in calls:`）同样按第 5 点加 `self.trace.tool(...)`（用 `c.name` / `c.arguments` / `c.id`）。

**Step 4: 跑测试**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_orchestrator.py -q`
Expected: 全绿（新增 3 个用例 + 原有用例不回归）

**Step 5: 全量回归 + lint + 提交**

```bash
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
git add backend/app/agent/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat(agent): 手写 Orchestrator 产出同形状轨迹——对照引擎可回放，测试对称"
```

---

## Task 4: `chat.py` 落库轨迹 + SSE `done` 事件附带 payload

**Files:**
- Modify: `backend/app/api/routes/chat.py`
- Test: `backend/tests/test_trajectory_api.py`（新建）

**Step 1: 先做一次纯重构（独立提交，先重构后加功能）**

`chat.py` 目前 `extra` 组装在两处重复（`_persist` 与非流式/流式路径）。抽成一个函数（**行为完全不变**）：

```python
def _build_extra(
    audit: list[dict] | None = None,
    pending: list[dict] | None = None,
    citations: list[dict] | None = None,
) -> dict:
    """组装助手消息的 Message.extra（工具审计 / 待确认 / 引用）。"""
    extra: dict = {}
    if audit:
        extra["tool_calls"] = audit
    if pending:
        extra["pending_confirmation"] = pending
    if citations:
        extra["citations"] = citations
    return extra
```

`_persist` 内改为 `extra = _build_extra(audit, pending, citations)`；流式路径内改为 `extra = _build_extra(audit, pending, citations)`。

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_chat_api.py tests/test_citations.py tests/test_hitl.py -q`
Expected: 全绿（重构不改行为）

```bash
git add backend/app/api/routes/chat.py
git commit -m "refactor(chat): 抽出 _build_extra——extra 组装两处重复，加字段易漏一处"
```

**Step 2: 写失败测试**

新建 `backend/tests/test_trajectory_api.py`：

```python
"""轨迹落库与 SSE 透传测试：Message.extra.trajectory + done 事件 payload。"""

import json
from typing import ClassVar

from httpx import ASGITransport, AsyncClient

from app.main import app

_FAKE_TRAJECTORY = {
    "engine": "langgraph",
    "total_ms": 120,
    "truncated": False,
    "steps": [
        {"type": "route", "route": "kb", "source": "llm", "ms": 40},
        {"type": "node", "node": "kb_agent"},
        {"type": "tool", "name": "kb_search", "arguments": "{}", "result": "片段", "status": "ok", "ms": 12},
        {"type": "answer", "chars": 6},
    ],
}


class _FakeAgent:
    last_tool_calls: ClassVar[list] = []
    pending_confirmation: ClassVar[list] = []
    last_citations: ClassVar[list] = []
    last_trajectory: ClassVar[dict] = _FAKE_TRAJECTORY

    async def run(self, **kwargs):
        return "回答"

    async def run_stream(self, **kwargs):
        yield "回答"

    async def close(self):
        pass


class _FakeAgentNoTrajectory(_FakeAgent):
    last_trajectory: ClassVar[dict] = {}


async def test_chat_persists_trajectory(monkeypatch, authed_headers: dict) -> None:
    """给定一条消息能复原 路由/节点/工具/结果（§10.5 验收）。"""
    from app.api.routes import chat as chat_module

    monkeypatch.setattr(chat_module, "_build_agent", lambda: _FakeAgent())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"message": "问个问题"}, headers=authed_headers)
        assert resp.status_code == 200, resp.text
        sid = resp.json()["data"]["session_id"]
        messages = (
            await client.get(f"/api/v1/sessions/{sid}/messages", headers=authed_headers)
        ).json()["data"]

    traj = messages[-1]["extra"]["trajectory"]
    assert traj["engine"] == "langgraph"
    assert [s["type"] for s in traj["steps"]] == ["route", "node", "tool", "answer"]
    assert traj["steps"][0]["route"] == "kb"
    assert traj["steps"][2]["name"] == "kb_search"


async def test_chat_omits_trajectory_when_engine_returns_empty(monkeypatch, authed_headers: dict) -> None:
    """引擎未产出轨迹（开关关闭）时不写空 key。"""
    from app.api.routes import chat as chat_module

    monkeypatch.setattr(chat_module, "_build_agent", lambda: _FakeAgentNoTrajectory())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"message": "你好"}, headers=authed_headers)
        sid = resp.json()["data"]["session_id"]
        messages = (
            await client.get(f"/api/v1/sessions/{sid}/messages", headers=authed_headers)
        ).json()["data"]
    assert "trajectory" not in (messages[-1]["extra"] or {})


async def test_chat_stream_done_event_carries_trajectory(monkeypatch, authed_headers: dict) -> None:
    """SSE done 事件增量附带 trajectory（不新增事件类型、不改既有事件形状）。"""
    from app.api.routes import chat as chat_module

    monkeypatch.setattr(chat_module, "_build_agent", lambda: _FakeAgent())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST", "/api/v1/chat/stream", json={"message": "你好"}, headers=authed_headers
        ) as resp:
            events: list[str] = []
            done_payload: dict = {}
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line[7:])
                elif line.startswith("data: "):
                    body = json.loads(line[6:])
                    if "trajectory" in body:
                        done_payload = body

    assert events[0] == "session" and events[-1] == "done"
    assert done_payload["trajectory"]["steps"][2]["name"] == "kb_search"
```

> 说明：`_FakeAgent.run_stream` 必须是**异步生成器**（`async def` + `yield`），否则流式路径迭代会失败。

**Step 3: 跑测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_trajectory_api.py -q`
Expected: FAIL —— `KeyError: 'trajectory'` / `done_payload` 为空

**Step 4: 实现**

`chat.py`：

1. `_build_extra` 增加 `trajectory: dict | None = None` 形参与落库分支：

```python
    if trajectory:
        extra["trajectory"] = trajectory
```

2. `_run_agent` 返回 5 元组：

```python
async def _run_agent(
    db: AsyncSession, history: list[dict], message: str, user_id
) -> tuple[str, list[dict], list[dict], list[dict], dict]:
    """执行一轮对话，返回 (回复, 工具审计, 待确认操作, 检索引用, 轨迹)。"""
    ...
        return (
            reply,
            list(getattr(agent, "last_tool_calls", [])),
            list(getattr(agent, "pending_confirmation", [])),
            list(getattr(agent, "last_citations", [])),
            dict(getattr(agent, "last_trajectory", None) or {}),
        )
```

3. `_persist` 增加 `trajectory: dict | None = None` 形参，并传给 `_build_extra`。
4. 非流式 `/chat`：解包 5 元组并透传：

```python
    reply, audit, pending, citations, trajectory = await _run_agent(
        db, history, req.message, user.id
    )
    ...
    await _persist(db, session.id, req.message, reply, audit, pending, citations, trajectory)
```

5. 流式 `/chat/stream` 的落库分支与 done 事件：

```python
            citations = list(getattr(agent, "last_citations", []))
            trajectory = dict(getattr(agent, "last_trajectory", None) or {})
            extra = _build_extra(audit, pending, citations, trajectory)
```
```python
            if pending:
                # 挂起确认事件（human-in-the-loop）：前端据此展示确认按钮
                yield _sse("pending", {"actions": pending})
            # done 语义不变（已持久化）；trajectory 为增量可选字段
            yield _sse("done", {"trajectory": trajectory} if trajectory else {})
```

> 不要给 `_persist_partial` 加轨迹：中断路径没有完整轨迹，故意留空。

**Step 5: 跑测试 + 全量回归 + lint + 提交**

```bash
.venv\Scripts\python.exe -m pytest tests/test_trajectory_api.py tests/test_chat_api.py -q
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
git add backend/app/api/routes/chat.py backend/tests/test_trajectory_api.py
git commit -m "feat(api): 轨迹落库与 SSE 透传——Message.extra.trajectory + done 事件增量字段"
```

---

## Task 5: 前端类型 + `TrajectoryPanel` 组件

**Files:**
- Modify: `web/src/types.ts`
- Create: `web/src/components/TrajectoryPanel.tsx`
- Create: `web/src/components/TrajectoryPanel.test.tsx`

**Step 1: 加类型**

`web/src/types.ts`：在 `PendingAction` 之前插入，并在 `ChatMessage.extra` 里加 `trajectory?: Trajectory;`：

```ts
/** Agent 轨迹单步：路由 / 节点 / 工具 / 回复（与后端 step 词汇表一一对应）。 */
export interface TrajectoryStep {
  type: "route" | "node" | "tool" | "answer";
  /** type=route */
  route?: string;
  source?: "llm" | "keyword";
  /** type=node */
  node?: string;
  /** type=tool */
  name?: string;
  arguments?: string;
  result?: string;
  status?: "ok" | "pending_confirmation";
  /** type=answer */
  chars?: number;
  /** 该步耗时（毫秒；route/tool 有） */
  ms?: number;
}

/** 一次回答的完整轨迹（后端规范化后落 Message.extra.trajectory）。 */
export interface Trajectory {
  engine: string;
  total_ms: number;
  truncated: boolean;
  steps: TrajectoryStep[];
}
```

**Step 2: 写失败测试**

创建 `web/src/components/TrajectoryPanel.test.tsx`：

```tsx
/** TrajectoryPanel 冒烟测试：空轨迹不渲染；展开后可见路由/节点/工具/耗时。 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Trajectory } from "../types";
import TrajectoryPanel from "./TrajectoryPanel";

const trajectory: Trajectory = {
  engine: "langgraph",
  total_ms: 120,
  truncated: false,
  steps: [
    { type: "route", route: "kb", source: "llm", ms: 40 },
    { type: "node", node: "kb_agent" },
    {
      type: "tool",
      name: "kb_search",
      arguments: '{"query":"x"}',
      result: "片段",
      status: "ok",
      ms: 12,
    },
    { type: "answer", chars: 6 },
  ],
};

describe("TrajectoryPanel", () => {
  it("无轨迹时不渲染", () => {
    const { container } = render(<TrajectoryPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("steps 为空时不渲染", () => {
    const { container } = render(
      <TrajectoryPanel trajectory={{ ...trajectory, steps: [] }} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("展开后展示引擎/步数/总耗时与各步内容", () => {
    render(<TrajectoryPanel trajectory={trajectory} />);
    const header = screen.getByText(/本次回答轨迹/);
    expect(header).toBeInTheDocument();
    expect(screen.getByText(/4 步/)).toBeInTheDocument();
    expect(screen.getByText(/120ms/)).toBeInTheDocument();

    fireEvent.click(header);

    expect(screen.getByText("kb_agent")).toBeInTheDocument();
    expect(screen.getByText("kb_search")).toBeInTheDocument();
    expect(screen.getByText(/40ms/)).toBeInTheDocument();
    expect(screen.getByText(/关键词兜底|模型判定/)).toBeInTheDocument();
  });

  it("截断时标注「已截断」", () => {
    render(<TrajectoryPanel trajectory={{ ...trajectory, truncated: true }} />);
    expect(screen.getByText(/已截断/)).toBeInTheDocument();
  });

  it("待确认的工具步标注未执行", () => {
    render(
      <TrajectoryPanel
        trajectory={{
          ...trajectory,
          steps: [
            { type: "tool", name: "todo_create", arguments: "{}", status: "pending_confirmation" },
          ],
        }}
      />
    );
    fireEvent.click(screen.getByText(/本次回答轨迹/));
    expect(screen.getByText(/待确认/)).toBeInTheDocument();
  });
});
```

**Step 3: 跑测试确认失败**

Run: `cd web && npx vitest run src/components/TrajectoryPanel.test.tsx`
Expected: FAIL —— 无法解析 `./TrajectoryPanel`

**Step 4: 实现 `TrajectoryPanel.tsx`**

```tsx
/**
 * 回答轨迹面板：让「多智能体不是黑盒」——展开可见 路由 → 节点 → 工具 → 耗时。
 *
 * 轨迹内容（工具参数/结果）来自模型与外部数据，一律用 React 默认转义渲染，
 * 禁止 dangerouslySetInnerHTML（AGENTS §5）。
 */

import { Collapse, Tag, Typography } from "antd";

import type { Trajectory, TrajectoryStep } from "../types";

const { Text } = Typography;

const ENGINE_LABEL: Record<string, string> = {
  langgraph: "LangGraph",
  handwritten: "手写 ReAct",
};

function msTag(ms?: number) {
  if (typeof ms !== "number") return null;
  return (
    <Text type="secondary" style={{ fontSize: 12 }}>
      {" "}
      {ms}ms
    </Text>
  );
}

function StepDetail({ step }: { step: TrajectoryStep }) {
  if (step.type === "route") {
    return (
      <>
        <Tag color="blue">路由</Tag>
        <Text code>{step.route}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {" "}
          （{step.source === "llm" ? "模型判定" : "关键词兜底"}）
        </Text>
        {msTag(step.ms)}
      </>
    );
  }
  if (step.type === "node") {
    return (
      <>
        <Tag color="purple">节点</Tag>
        <Text code>{step.node}</Text>
      </>
    );
  }
  if (step.type === "tool") {
    const pending = step.status === "pending_confirmation";
    return (
      <>
        <Tag color={pending ? "orange" : "green"}>工具</Tag>
        <Text code>{step.name}</Text>
        {pending && (
          <Text type="warning" style={{ fontSize: 12 }}>
            {" "}
            （待确认，尚未执行）
          </Text>
        )}
        {msTag(step.ms)}
        <div className="dim" style={{ fontSize: 12, wordBreak: "break-all" }}>
          参数：{step.arguments || "{}"}
        </div>
        {step.result && (
          <div className="dim" style={{ fontSize: 12, wordBreak: "break-all" }}>
            结果：{step.result}
          </div>
        )}
      </>
    );
  }
  return (
    <>
      <Tag>回复</Tag>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {step.chars ?? 0} 字
      </Text>
    </>
  );
}

export default function TrajectoryPanel({ trajectory }: { trajectory?: Trajectory }) {
  if (!trajectory || !trajectory.steps?.length) return null;
  const summary = `${ENGINE_LABEL[trajectory.engine] ?? trajectory.engine} · ${
    trajectory.steps.length
  } 步 · ${trajectory.total_ms}ms${trajectory.truncated ? " · 已截断" : ""}`;
  return (
    <Collapse
      size="small"
      className="trajectory-panel"
      items={[
        {
          key: "trajectory",
          label: (
            <span>
              本次回答轨迹
              <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                {summary}
              </Text>
            </span>
          ),
          children: (
            <ol className="trajectory-steps" style={{ margin: 0, paddingLeft: 18 }}>
              {trajectory.steps.map((step, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  <StepDetail step={step} />
                </li>
              ))}
            </ol>
          ),
        },
      ]}
    />
  );
}
```

**Step 5: 跑测试 + build**

Run: `cd web && npx vitest run src/components/TrajectoryPanel.test.tsx && npm run build`
Expected: 5 passed；`tsc -b` 零错误

**Step 6: 提交**

```bash
git add web/src/types.ts web/src/components/TrajectoryPanel.tsx web/src/components/TrajectoryPanel.test.tsx
git commit -m "feat(web): 新增 TrajectoryPanel——回答轨迹可展开查看（路由/节点/工具/耗时）"
```

---

## Task 6: `ChatPanel` 接入（SSE `done` payload → 消息 extra → 渲染）

**Files:**
- Modify: `web/src/api.ts`（`StreamHandlers.onDone` 签名 + `trajectory` 透传）
- Modify: `web/src/components/ChatPanel.tsx`
- Test: `web/src/components/ChatPanel.test.tsx`

**Step 1: 写失败测试**

追加到 `web/src/components/ChatPanel.test.tsx`：

```tsx
  it("done 事件带 trajectory 时在气泡内渲染轨迹面板", async () => {
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      handlers.onChunk("回答");
      handlers.onDone({
        trajectory: {
          engine: "langgraph",
          total_ms: 88,
          truncated: false,
          steps: [{ type: "route", route: "tools", source: "keyword", ms: 5 }],
        },
      });
    });

    renderPanel();
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "测试问题" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    expect(await screen.findByText(/本次回答轨迹/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/本次回答轨迹/));
    expect(screen.getByText(/关键词兜底/)).toBeInTheDocument();
  });

  it("历史消息自带 trajectory 时也能渲染（刷新后回放）", () => {
    renderPanel({
      initialMessages: [
        {
          role: "assistant",
          content: "答案",
          extra: {
            trajectory: {
              engine: "handwritten",
              total_ms: 30,
              truncated: false,
              steps: [{ type: "node", node: "orchestrator" }],
            },
          },
        },
      ],
    });
    expect(screen.getByText(/本次回答轨迹/)).toBeInTheDocument();
  });

  it("done 无 trajectory 时仍复位 busy 且不渲染面板", async () => {
    const setBusy = vi.fn();
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      handlers.onChunk("回答");
      handlers.onDone();
    });

    renderPanel({ setBusy });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => expect(setBusy).toHaveBeenCalledWith(false));
    expect(screen.queryByText(/本次回答轨迹/)).not.toBeInTheDocument();
  });
```

**Step 2: 跑测试确认失败**

Run: `cd web && npx vitest run src/components/ChatPanel.test.tsx -t trajectory`
Expected: FAIL —— 轨迹面板未渲染

**Step 3: 实现**

`web/src/api.ts`：

1. `import type { ..., Trajectory, ... } from "./types";`
2. `StreamHandlers`：

```ts
  /** 完成（后端已持久化）；data 中可能带本轮轨迹（旧后端可能不带） */
  onDone: (payload?: { trajectory?: Trajectory }) => void;
```

3. `payload` 局部类型加 `trajectory?: Trajectory;`
4. 分发处改为 `else if (event === "done") handlers.onDone(payload);`

`web/src/components/ChatPanel.tsx`：

1. `import TrajectoryPanel from "./TrajectoryPanel";`
2. `onDone` 改为合并 extra（与既有 `onPending` 同构），并**保证 busy 一定复位**：

```tsx
        onDone: (payload) => {
          // 轨迹落库随 done 一并到达（旧后端不带）：合并到最后一条助手消息
          if (payload?.trajectory) {
            setMessages((prev) => {
              const next = [...prev];
              const lastIdx = next.length - 1;
              const last = next[lastIdx];
              if (last && last.role === "assistant") {
                next[lastIdx] = {
                  ...last,
                  extra: { ...(last.extra || {}), trajectory: payload.trajectory },
                };
              }
              return next;
            });
          }
          setBusy(false);
        },
```

3. 在引用来源块之后、气泡 `</div>` 之前渲染面板：

```tsx
              {m.role === "assistant" && m.extra?.trajectory && (
                <TrajectoryPanel trajectory={m.extra.trajectory} />
              )}
```

**Step 4: 跑测试 + 全量 + build**

Run: `cd web && npx vitest run && npm run build`
Expected: 全部通过（原 92 + 新增 8 = 100，实际以输出为准）；`tsc -b` 零错误

**Step 5: 提交**

```bash
git add web/src/api.ts web/src/components/ChatPanel.tsx web/src/components/ChatPanel.test.tsx
git commit -m "feat(web): ChatPanel 渲染回答轨迹——done 事件合并 extra，历史消息同样可回放"
```

---

## Task 7: 全量验收 + 主仓库进度回填

**Files:**
- Modify: `OPTIMIZATION_PLAN.md`（§13 路线图 R2 打勾 + §14 基线数字）
- Test: 无新增（本任务是验收）

**Step 1: 跑全量门槛**

```bash
cd backend
.venv\Scripts\python.exe -m pytest -q          # 期望：全绿，覆盖率 ≥80%
.venv\Scripts\ruff.exe check .                 # 期望：All checks passed
cd ..\cli && .venv\Scripts\python.exe -m pytest -q   # 若存在独立 venv；否则用 backend 的 python -m pytest tests
cd ..\web
npx vitest run                                 # 期望：全绿
npm run build                                  # 期望：零错误
```

**Step 2: 人工核对三条验收（§10.5 中属于 R2 的三条）**

- [ ] **trajectory 可回放**：`tests/test_trajectory_api.py::test_chat_persists_trajectory` 用一条消息复原了 路由/节点/工具/结果
- [ ] **两引擎同形状**：`tests/test_orchestrator.py` 与 `tests/test_langgraph_engine.py` 的轨迹用例都过
- [ ] **无密钥**：`tests/test_langgraph_engine.py::test_trajectory_no_secret_leak` + `tests/test_trajectory.py::test_sensitive_keys_are_masked` 都过

**Step 3: 回填 `OPTIMIZATION_PLAN.md`**

- §13 路线图：`- [ ] **R2** Q1 trajectory 落库与前端展示` → `- [x]`（并把行尾预估"~3 天"替换为实际）
- §13 表格 R2 行「验收位置」保持「镜头 2」不变
- §14 基线快照：更新 `337 / 82.53%` → 实测数字，前端 `92` → 实测数字，并注明 `@ <R2 tip 短 SHA>`

**Step 4: 提交**

```bash
git add OPTIMIZATION_PLAN.md
git commit -m "docs(plan): R2 完成——trajectory 落库与前端可见，验收基线更新"
```

---

## Task 8: 复盘记录文档（`private-docs`）

**Files:**
- Modify: `C:/Users/asus/Documents/copilot-lite-private/docs/优化落地记录.md`（追加「批次 R2」一节）

**评审方式**：文档任务，**不生成 diff 包**；评审者直接读被改文件 + 本任务要求，核对下列五要素齐全、数字与 Task 7 实测一致、无密钥/无对话原文。

**内容模板**（照该文件既有「批次 L」小节的写法）：

```markdown
## 十四、批次 R2 · Q1 回答轨迹（可观测地基）

**实现（分支 `feat/agent-trajectory`，提交 `<base7>..<tip7>`）**
- **轨道契约**：`app/agent/trajectory.py` 的 `TrajectoryRecorder`——两个引擎产出同形状轨迹
  （`route`/`node`/`tool`/`answer`），落库前统一规范化。
- **规范化口径**：≤20 步、参数 ≤300 字符、结果 ≤500 字符、总量 ≤16KB，超限 `truncated: true`；
  敏感 key（api_key/secret/token/...）值替换 `***`，`max_tokens` 不误伤。
- **两引擎接线**：LangGraph 记录路由来源（`llm`/`keyword`）+ 节点 + 工具耗时；
  手写 `Orchestrator` 同形状（无 `route` step——它没有路由能力）。
- **落库与透传**：`Message.extra.trajectory`；SSE `done` 事件**增量**附带 `trajectory`
  （不新增事件类型，旧前端忽略即可）。
- **前端**：`TrajectoryPanel` 组件 + `ChatPanel` 气泡内渲染；刷新后从历史消息回放。
- **配置三件套**：`AGENT_TRACE_ENABLED`（config + 两份模板 + conftest 默认关）。

**原理**：多智能体没有轨迹就不可调试、不可评测（Q0.7）——先补可观测再扩子 Agent。

**踩坑**：（如实记录本批实际踩的坑；至少覆盖：GBK 控制台核对中文 / 敏感 key 正则误伤 `max_tokens` /
手写引擎 6 个出口点漏记 / vitest 慢在哪）

**测试结果**：后端 `<N>` 用例 / 覆盖率 `<X>%`、ruff 全过；前端 `<M>` 用例、build 零错误。

**面试一句话话术**：多智能体不是黑盒——每次回答的路由判定、选中子 Agent、工具调用序列与各步耗时
全量落库并可展开回放；轨迹与密钥做了硬隔离（正则脱敏 + 用例守护）。

**冻结候选（本批发现但未做）**：<如实记录；无则写"无">
```

**提交**（在私有工作区）：

```bash
cd C:/Users/asus/Documents/copilot-lite-private
git add docs/优化落地记录.md
git commit -m "docs: R2 落地记录——回答轨迹落库与前端可见"
```

---

## 交付物清单

- 后端：`app/agent/trajectory.py`（新）、`langgraph_engine.py`、`orchestrator.py`、`base.py`、`api/routes/chat.py`、`core/config.py`、`tests/conftest.py`、`tests/test_trajectory.py`（新）、`tests/test_trajectory_api.py`（新）、`tests/test_langgraph_engine.py`、`tests/test_orchestrator.py`
- 配置：`deploy/.env.example`、`backend/.env.example`
- 前端：`types.ts`、`api.ts`、`components/TrajectoryPanel.tsx`（新）、`components/TrajectoryPanel.test.tsx`（新）、`components/ChatPanel.tsx`、`components/ChatPanel.test.tsx`
- 文档：`OPTIMIZATION_PLAN.md`（主仓库）、`docs/优化落地记录.md`（private-docs）

## 留给下一批的接口（不实现）

- R3 引用来源标注可复用 `TrajectoryPanel` 所在位置（消息气泡内的附加面板区）；
- R5 双引擎对照评测可直接消费 `Message.extra.trajectory` 的 `engine` 与 `total_ms`。
