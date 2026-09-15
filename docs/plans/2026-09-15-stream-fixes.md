# 流式链路修复（心跳截断 / 独白泄漏 / 新会话首条自杀）实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修掉真实使用中暴露的三个流式缺陷——① 心跳超时静默取消生成器导致回答被截断却仍报 `done`；② 工具轮的模型独白被当成回答流出/落库；③ 新会话首条消息被自身的会话切换 effect 取消。

**Architecture:** 三处各自最小改动。① `chat.py` 的心跳改为「保持同一个 `anext` Task 不取消」+ 加整体上限；② 两个引擎的 `run_stream` 改为**按模型轮缓冲**：该轮有 `tool_calls` 就丢弃该轮文本，无 `tool_calls` 才产出；对**不挂工具的 Agent**（`chat_agent`）保持逐字流式（那类轮次不可能有工具调用，缓冲无收益）；③ `ChatPanel` 的 abort 改为「仅真正切换会话时取消」，并把「同步 initialMessages」与「取消进行中的流」拆成两个 effect。

**Tech Stack:** Python 3.12 / FastAPI / asyncio / LangGraph / langchain-core；React 18 + TS + Ant Design + vitest。

---

## Global Constraints

> 实现者与评审者都按此逐条核对。

1. **工作目录**：主仓库 `C:/Users/asus/Documents/copilot-lite`，分支 `fix/stream-truncation`，基线 `8d79c11`。私有文档在 `C:/Users/asus/Documents/copilot-lite-private`。
2. **控制台是 GBK**：核对中文一律 `python -c "print(ascii(...))"`，不要靠肉眼读终端。
3. **提交规范**（AGENTS §3）：Conventional Commits，中文描述，**一个提交 = 一个问题**。
4. **不新增/不改名 SSE 事件**：`session` / `chunk` / `pending` / `error` / `done` 五个事件名与语义保持不变。本计划**不允许**通过新增「撤回/替换」事件来修复独白泄漏。
5. **`done` 的语义必须诚实**：`done` = 整轮回答已完整产出并落库。**任何**「回答被截断」的路径都不得走 `done`，必须走 `error`（并保留已有的部分落库行为）。
6. **逐字流式的保留范围**：**不挂工具的 Agent**（`chat_agent`、以及手写引擎以外的纯文本轮）必须继续逐字产出。挂工具的轮次改为「该轮结束时一次性产出」，这是**已知且被接受的取舍**（见下方 Ruling）。
7. **防回归测试必须先失败**：每个修复都要有一个在修复前失败的用例，报告中给出 RED 与 GREEN 两段证据。
8. **不得改动**：`Message.extra` 的键名与形状、轨迹词汇表、`_persist_partial` 的「无 extra」行为、`AGENT_ENGINE` 双引擎并存结构。
9. **门槛**：后端 `pytest` 全绿 + 覆盖率 ≥80% + `ruff check .` 全过；前端 `npx vitest run` 全绿 + `npm run build` 零错误。
10. **串行跑测试**：所有 pytest 共用 `copilot_test` 库，**禁止并行**，否则 fixture 会 `ERROR at setup`。

### Ruling（控制者已定，不再讨论）

**独白泄漏用「按轮缓冲」修，而不是新增 SSE 撤回事件。** 代价：挂工具的轮次的文本不再逐字出现，而是在该轮结束时整段出现；不挂工具的轮次（纯聊天）保持逐字。若日后要两者兼得，做法是新增一个 additive 的「替换正文」事件，属独立改动，不在本次范围。

---

## Task 1: 心跳不再取消生成器（回答截断却报 `done`）

**背景（必读）**：`backend/app/api/routes/chat.py` 现在用
`text = await asyncio.wait_for(anext(agent_stream), timeout=_HEARTBEAT_SECONDS)`。
`asyncio.wait_for` 超时**会取消**它包裹的协程 —— 而 `anext()` 被取消就等于把异步生成器就地终止。
之后 `continue` 再 `anext()` 只会抛 `StopAsyncIteration`，被 `except StopAsyncIteration: break` 当成
「流正常结束」→ 走 `else:` 分支落库 + 发 `done`。后果：静默期 >15s 的长工具轮（如 `kb_search` 走 3 路
查询改写）会被**静默截断**，用户拿到半截独白却看到「成功」；且 `run_stream` 的收尾代码没跑，
`last_citations` / `last_trajectory` 一起丢（已实测：`extra` 里只剩 `tool_calls`，连 `citations` 都没有）。

**Files:**
- Modify: `backend/app/api/routes/chat.py`（模块常量区 + 流循环）
- Test: `backend/tests/test_chat_stream_heartbeat.py`（新建）

**Step 1: 写失败测试**

新建 `backend/tests/test_chat_stream_heartbeat.py`：

```python
"""流式心跳：长静默期不得截断回答，也不得把截断当成 done。

回归对象：`asyncio.wait_for(anext(gen), ...)` 超时会取消生成器，导致
「静默 > 心跳间隔」的轮次被静默截断、且仍发 done。
"""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


class _SlowStreamAgent:
    """模拟长静默期的流式产出：分片之间 sleep 超过心跳间隔。"""

    last_tool_calls: list = []
    pending_confirmation: list = []
    last_citations: list = [{"index": 1, "chunk_id": "c1", "source": "文档X", "snippet": "s"}]
    last_trajectory: dict = {
        "engine": "langgraph",
        "total_ms": 1,
        "truncated": False,
        "steps": [{"type": "answer", "chars": 4}],
    }

    def __init__(self, parts: list[str], gap: float) -> None:
        self._parts = parts
        self._gap = gap

    async def run_stream(self, **kwargs):
        for p in self._parts:
            await asyncio.sleep(self._gap)
            yield p

    async def close(self) -> None:
        pass


async def _drain(client, headers) -> tuple[list[str], dict, list[str], list[str]]:
    events: list[str] = []
    texts: list[str] = []
    done: dict = {}
    errors: list[str] = []
    async with client.stream(
        "POST", "/api/v1/chat/stream", json={"message": "长静默测试"}, headers=headers
    ) as resp:
        event = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event = line[7:]
                events.append(event)
            elif line.startswith("data: "):
                payload = json.loads(line[6:])
                if event == "chunk" and "text" in payload:
                    texts.append(payload["text"])
                elif event == "done":
                    done = payload
                elif event == "error":
                    errors.append(payload.get("detail", ""))
    return events, done, texts, errors


async def test_slow_round_is_not_truncated(monkeypatch, authed_headers):
    """分片间隔 > 心跳间隔时，全部分片都要到达，且要发 done。"""
    from app.api.routes import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_HEARTBEAT_SECONDS", 0.05)
    agent = _SlowStreamAgent(["第一段", "第二段", "第三段"], gap=0.15)
    monkeypatch.setattr(chat_mod, "_build_agent", lambda: agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        events, done, texts, errors = await _drain(client, authed_headers)

    assert "".join(texts) == "第一段第二段第三段", f"回答被截断：{texts!r}"
    assert "done" in events and not errors


async def test_slow_round_keeps_trajectory_and_citations(monkeypatch, authed_headers):
    """收尾代码必须跑到：citations 与 trajectory 都要落库（截断时两者会一起丢）。"""
    from app.api.routes import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_HEARTBEAT_SECONDS", 0.05)
    agent = _SlowStreamAgent(["完整回答"], gap=0.15)
    monkeypatch.setattr(chat_mod, "_build_agent", lambda: agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, _, _, _ = await _drain(client, authed_headers)
        sid = None
        sessions = (await client.get("/api/v1/sessions", headers=authed_headers)).json()["data"]
        sid = sessions[0]["id"]
        msgs = (
            await client.get(f"/api/v1/sessions/{sid}/messages", headers=authed_headers)
        ).json()["data"]

    extra = msgs[-1].get("extra") or {}
    assert "citations" in extra, "收尾未执行：citations 丢失"
    assert "trajectory" in extra, "收尾未执行：trajectory 丢失"
    assert msgs[-1]["content"] == "完整回答"
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_chat_stream_heartbeat.py -q`
Expected: FAIL —— 回答只剩第一段（`'第一段' != '第一段第二段第三段'`），且 extra 里没有 citations/trajectory

**Step 3: 实现**

`chat.py` 模块常量区（`_HEARTBEAT_SECONDS` 附近）加：

```python
# 单次流式请求的总时长上限（秒）：心跳只负责保活，不负责兜底；
# 没有总量上限时，一个真正挂死的生成器会无限发心跳、长期占用连接与 DB 会话。
_STREAM_MAX_SECONDS = 600.0
```

流循环改为「同一个 `anext` Task 跨心跳存活」：

```python
            agent_stream = agent.run_stream(
                session=db, user_id=user.id, history=history, user_message=req.message
            )
            # 心跳：等待下一分片的同时按 _HEARTBEAT_SECONDS 发保活注释。
            # 必须把 anext 挂成一个 Task 并跨超时复用——不能用 asyncio.wait_for，
            # 它超时会取消被包裹的 anext，把生成器就地终止（回答被静默截断却仍发 done）。
            stream_started = asyncio.get_running_loop().time()
            pending = asyncio.ensure_future(anext(agent_stream))
            while True:
                done_set, _ = await asyncio.wait({pending}, timeout=_HEARTBEAT_SECONDS)
                if not done_set:
                    if asyncio.get_running_loop().time() - stream_started > _STREAM_MAX_SECONDS:
                        pending.cancel()
                        raise HTTPException(status_code=504, detail="生成超时，请重试")
                    yield ": ping\n\n"
                    continue
                try:
                    text = pending.result()
                except StopAsyncIteration:
                    break
                pending = asyncio.ensure_future(anext(agent_stream))
                reply_parts.append(text)
                yield _sse("chunk", {"text": text})
```

注意：
- `raise HTTPException(504, ...)` 会落到既有的 `except HTTPException` 分支：`_persist_partial` 落已产出的部分 + 发 `error` 事件。**这正是我们要的**——截断必须报 error，不能报 done。
- 不要改动 `except StopAsyncIteration` 之外的分支结构与顺序。

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_chat_stream_heartbeat.py -q`
Expected: `2 passed`

**Step 5: 全量 + lint + 提交**

```bash
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
git add backend/app/api/routes/chat.py backend/tests/test_chat_stream_heartbeat.py
git commit -m "fix(chat): 心跳不再取消生成器——静默超时曾把回答拦腰截断却仍报 done（并丢轨迹与引用）"
```

---

## Task 2: 工具轮的独白不再当作回答（双引擎按轮缓冲）

**背景（必读）**：模型在**调用工具的那一轮**会同时输出 `content`（如 `"I'll check your todo list for you."`）。
两个引擎的 `run_stream` 都把这类 content 直接转发/落库，于是回答变成
`"I'll check your todo list for you.你的待办列表如下：…"`。
`orchestrator.py` 的注释里写着「工具调用轮 content 为空、纯文本轮 tool_calls 为空，二者互斥」——
**这个假设被 DeepSeek 打破**，两个引擎都基于它写了转发逻辑。

**Files:**
- Modify: `backend/app/agent/langgraph_engine.py`（`run_stream`）
- Modify: `backend/app/agent/orchestrator.py`（`run_stream`）
- Test: `backend/tests/test_stream_no_narration.py`（新建）

**Step 1: 写失败测试**

新建 `backend/tests/test_stream_no_narration.py`：

```python
"""工具轮的模型独白不得当作回答产出（两个引擎同测）。

回归对象：模型在 tool_calls 那一轮同时输出 content（如 "I'll search …"），
被 run_stream 原样转发/落库，回答变成「英文独白 + 真答案」。
"""

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agent.langgraph_engine import LangGraphEngine
from app.agent.orchestrator import Orchestrator
from app.core.constants import DEFAULT_USER_ID
from app.core.llm import ChatResult, ToolCall
from app.tools import registry


class _FakeToolChatModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _route_msg(route: str) -> AIMessage:
    return AIMessage(content=f'{{"route": "{route}", "reason": "测试"}}')


# ---------- LangGraph ----------


@pytest.mark.asyncio
async def test_langgraph_stream_drops_tool_round_narration(db_session) -> None:
    """第一轮带 tool_calls 且 content 是独白 → 独白不得出现；只产出最终答案。"""
    llm = _FakeToolChatModel(
        messages=iter(
            [
                _route_msg("tools"),
                AIMessage(
                    content="I'll check your todo list for you.",
                    tool_calls=[{"name": "todo_list", "args": {}, "id": "c1"}],
                ),
                AIMessage(content="你的待办是空的。"),
            ]
        )
    )
    engine = LangGraphEngine(llm=llm, registry=registry, max_turns=3)
    parts = [p async for p in engine.run_stream(db_session, DEFAULT_USER_ID, [], "看下待办")]

    text = "".join(parts)
    assert text == "你的待办是空的。", f"独白泄漏：{text!r}"


@pytest.mark.asyncio
async def test_langgraph_stream_keeps_plain_chat_progressive(db_session) -> None:
    """不挂工具的 chat_agent：仍逐字产出（缓冲对这类轮次无收益，不应牺牲流式）。"""
    llm = _FakeToolChatModel(
        messages=iter([_route_msg("chat"), AIMessage(content="你好呀")])
    )
    engine = LangGraphEngine(llm=llm, registry=registry, max_turns=3)
    parts = [p async for p in engine.run_stream(db_session, DEFAULT_USER_ID, [], "你好")]

    assert "".join(parts) == "你好呀"


# ---------- 手写 Orchestrator ----------


class _FakeStreamLLM:
    """按预设轮次返回：每轮给出若干 content 分片 + 可选 tool_calls。"""

    def __init__(self, rounds) -> None:
        self._rounds = list(rounds)

    async def stream_raw(self, messages, tools=None, temperature=0.7):
        round_ = self._rounds.pop(0)

        class _Delta:
            def __init__(self, content=None, tool_calls=None):
                self.content = content
                self.tool_calls = tool_calls

        class _Choice:
            def __init__(self, delta):
                self.delta = delta

        class _Chunk:
            def __init__(self, delta):
                self.choices = [_Choice(delta)]

        for piece in round_["content"]:
            yield _Chunk(_Delta(content=piece))
        for tc in round_.get("tool_calls", []):
            yield _Chunk(_Delta(tool_calls=[tc]))

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_orchestrator_stream_drops_tool_round_narration(db_session) -> None:
    from app.core.llm import ToolCall as _TC

    llm = _FakeStreamLLM(
        [
            {
                "content": ["I'll look that up for you."],
                "tool_calls": [_TC(id="c1", name="todo_list", arguments="{}")],
            },
            {"content": ["你的", "待办是空的。"]},
        ]
    )
    orch = Orchestrator(llm=llm, registry=registry, max_turns=3)
    parts = [p async for p in orch.run_stream(db_session, DEFAULT_USER_ID, [], "看下待办")]

    text = "".join(parts)
    assert text == "你的待办是空的。", f"独白泄漏：{text!r}"
```

> 注：手写引擎的 fake **复用 `tests/test_orchestrator.py:142` 既有的 `StreamFakeLLM`**
> （已有 `stream_raw`，且被既有流式用例验证过），不要新造一套；上面的 `_FakeStreamLLM` 只是形状参考。
> 另：`pyproject.toml` 设了 `asyncio_mode = "auto"`，`@pytest.mark.asyncio` 可省（写了也无害）。

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_stream_no_narration.py -q`
Expected: 两个 `drops_tool_round_narration` FAIL（文本以 `I'll …` 开头）

**Step 3: 实现**

`langgraph_engine.py` 的 `run_stream`：把 `astream_events` 循环改为**按模型轮缓冲**，用
`on_chat_model_start` / `on_chat_model_end` 划分轮次，`on_chat_model_end` 的 `output.tool_calls` 决定丢弃或产出：

```python
        leaf_nodes = ("kb_agent", "tools_agent", "chat_agent")
        yielded = False
        chars = 0
        round_parts: list[str] = []
        async for event in self.graph.astream_events(state, version="v2"):
            node = (event.get("metadata") or {}).get("langgraph_node")
            if node not in leaf_nodes:
                continue  # Supervisor 等内部输出不泄漏给用户
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = getattr(event["data"].get("chunk"), "content", None)
                if not isinstance(content, str) or not content:
                    continue
                if _binds_no_tools(node):
                    # 该类节点不可能有工具调用 → 直接逐字产出（保住流式体验）
                    yielded = True
                    chars += len(content)
                    yield content
                else:
                    round_parts.append(content)
            elif kind == "on_chat_model_end":
                if _binds_no_tools(node):
                    continue
                text = ""
                if not (getattr(event["data"].get("output"), "tool_calls", None) or []):
                    # 无工具调用 = 该轮就是回答轮 → 产出
                    text = "".join(round_parts)
                round_parts = []
                if text:
                    yielded = True
                    chars += len(text)
                    yield text
```

并加模块级判定函数（放 `AGENT_TOOLS` 之后）：

```python
def _binds_no_tools(node_name: str) -> bool:
    """该子 Agent 是否**显式不挂任何工具**。

    只有显式空列表（`chat_agent`）才算无工具：`tools_agent` 的 `None` 语义是
    「全部工具」（见 `_tool_schemas`），绝不能用 falsy 判定把它误当成无工具。
    """
    return AGENT_TOOLS.get(node_name) == []
```

`orchestrator.py` 的 `run_stream`：把 `yield delta.content` 改为缓冲，本轮结束时按 `tool_calls` 决定：

```python
        for _ in range(self.max_turns):
            tool_calls: dict[int, dict] = {}
            round_parts: list[str] = []
            try:
                stream = await self.llm.stream_raw(messages, tools=self.registry.schemas())
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        round_parts.append(delta.content)
                    if delta and delta.tool_calls:
                        ...
            except Exception as exc:
                ...
            if not tool_calls:
                # 纯文本轮：本轮缓冲即回答（工具轮的独白在此被丢弃）
                text = "".join(round_parts)
                chars += len(text)
                self._seal_trajectory(chars)
                if text:
                    yield text
                return
```

并把 `for c in calls:` 之前把本轮 `round_parts` 丢弃（工具轮 = 不再使用），照原结构执行工具。

> 手写引擎**整体**不再逐字产出（它每轮都可能调工具，无法预判），这是 Ruling 里说明并接受的取舍；
> 在 docstring 里写明，不要留着「二者互斥」那句过时注释——改为说明「工具轮的 content 是独白，已丢弃」。

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_stream_no_narration.py tests/test_orchestrator.py tests/test_langgraph_engine.py -q`
Expected: 全绿

**Step 5: 全量 + lint + 提交**

```bash
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
git add backend/app/agent/langgraph_engine.py backend/app/agent/orchestrator.py backend/tests/test_stream_no_narration.py
git commit -m "fix(agent): 工具轮独白不再当作回答——双引擎按轮缓冲，去掉了被打破的互斥假设"
```

---

## Task 3: 新会话首条消息不再自我取消

**背景（必读）**：`ChatPanel.tsx` 里

```tsx
useEffect(() => {
  setMessages(initialMessages);
  abortRef.current?.abort();
}, [initialMessages, sessionId]);
```

而 `onSessionCreated={setSessionId}`：新会话首条消息发出后，SSE `session` 事件把 `sessionId` 从
`null` 变成新 id → 该 effect 触发 → **abort 掉刚刚发起的那条流** → `AbortError` →
气泡显示「生成出错：已停止生成」。同一 effect 的 `setMessages(initialMessages)` 还会把乐观插入的
用户消息与助手气泡重置掉。**新会话第一条必挂，之后正常**。

**Files:**
- Modify: `web/src/components/ChatPanel.tsx`
- Test: `web/src/components/ChatPanel.test.tsx`

**Step 1: 写失败测试**

追加到 `web/src/components/ChatPanel.test.tsx`：

```tsx
  it("新会话首条消息不被自身的会话创建取消（防「已停止生成」）", async () => {
    let signal: AbortSignal | undefined;
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      signal = handlers.signal;
      handlers.onSession("s-new");
      handlers.onChunk("回答");
      handlers.onDone();
    });

    const { rerender } = renderPanel({ sessionId: null });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "第一条" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => expect(mocked.streamChat).toHaveBeenCalled());
    // 模拟父组件收到 onSessionCreated 后把 sessionId 传下来
    rerender(<ChatPanel {...panelProps({ sessionId: "s-new" })} />);

    expect(signal?.aborted).toBe(false);
    await waitFor(() => expect(screen.getByText("回答")).toBeInTheDocument());
  });

  it("真正切换会话时仍会取消进行中的流（保住原意图）", async () => {
    let signal: AbortSignal | undefined;
    mocked.streamChat.mockImplementation(async (_msg, _sid, handlers) => {
      signal = handlers.signal;
      handlers.onSession("s-1");
      await new Promise(() => {}); // 永不结束，模拟进行中
    });

    const { rerender } = renderPanel({ sessionId: "s-1" });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    await waitFor(() => expect(mocked.streamChat).toHaveBeenCalled());

    rerender(<ChatPanel {...panelProps({ sessionId: "s-2" })} />);
    await waitFor(() => expect(signal?.aborted).toBe(true));
  });
```

> `panelProps(overrides)` 是为了让 rerender 用同一组 props 覆盖 —— 若现有测试里的 `renderPanel`
> 不便复用，就抽一个返回 props 的小工具函数（`renderPanel` 改为内部调用它）。
> **不要改动既有用例的行为。**

**Step 2: 跑测试确认失败**

Run: `cd web && npx vitest run src/components/ChatPanel.test.tsx -t 取消`
Expected: 第一条用例 FAIL（`signal.aborted` 为 `true`）

**Step 3: 实现**

```tsx
  const abortRef = useRef<AbortController | null>(null);
  // 进行中的流属于哪个会话：用于区分「新建会话（null→id）」与「真的切走了」
  const streamSessionRef = useRef<string | null>(null);

  useEffect(() => {
    setMessages(initialMessages);
  }, [initialMessages]);

  useEffect(() => {
    // 仅在真正切换到别的会话时取消进行中的流（防旧会话响应写入新会话）；
    // 新会话首条消息会经历 null→新 id，那不算切换，取消它 = 自己杀自己。
    const controller = abortRef.current;
    if (controller && sessionId !== streamSessionRef.current) controller.abort();
  }, [sessionId]);
```

`send()` 里维护 `streamSessionRef`：

```tsx
    const controller = new AbortController();
    abortRef.current = controller;
    streamSessionRef.current = sessionId;   // 本轮流属于哪个会话
    let currentSid = sessionId;
    try {
      await streamChat(text, currentSid, {
        signal: controller.signal,
        onSession: (sid) => {
          currentSid = sid;
          streamSessionRef.current = sid;   // 新会话建出来了，归属随之更新
          onSessionCreated(sid);
        },
```

`finally` 里一并清空：

```tsx
    } finally {
      setBusy(false);
      abortRef.current = null;
      streamSessionRef.current = null;
    }
```

**Step 4: 跑测试 + 全量 + build**

```bash
cd web
npx vitest run
npm run build
```
Expected: 全绿（原 102 + 新增 2），`tsc -b` 零错误

**Step 5: 提交**

```bash
git add web/src/components/ChatPanel.tsx web/src/components/ChatPanel.test.tsx
git commit -m "fix(web): 新会话首条消息不再自我取消——会话创建不等于切换会话"
```

---

## Task 4: 验收 + 记录文档 + 计划回填

**Files:**
- Modify: `OPTIMIZATION_PLAN.md`（§12 待合并与推送）
- Modify: `C:/Users/asus/Documents/copilot-lite-private/docs/优化落地记录.md`（追加一节）

**Step 1: 全量门槛（串行）**

```bash
cd backend && .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\ruff.exe check .
cd ..\web && npx vitest run && npm run build
```

**Step 2: 真实链路复验（关键，别再靠单测自证）**

对**运行中的服务**跑一次慢工具轮（`kb_search`，会触发 >15s 静默），确认三件事：
- 流式文本**是完整中文答案**，不再只有英文独白
- 落库 `extra` 同时含 `citations` 与 `trajectory`
- 事件序列仍以 `done` 结束（未截断）

把命令与原始输出贴进报告。若 `kb_search` 快到不触发静默，就用 `AGENT_MAX_TURNS` 或临时提高
检索耗时制造长静默（**必须在报告里说明是怎么制造的**，不要谎称是真实现象）。

**Step 3: 回填文档**

- `OPTIMIZATION_PLAN.md` §12：加一条待合并项（`fix/stream-truncation`，说明修了哪三个缺陷）。
- `private-docs` 的 `优化落地记录.md`：追加「批次 R2.1 · 流式链路三修」小节，含
  **改动 / 原理 / 踩坑 / 测试结果 / 面试一句话话术 / 冻结候选**（冻结候选写：若要「逐字流式 + 无独白」
  两者兼得，需新增 additive 的「替换正文」事件，属独立改动；`_STREAM_MAX_SECONDS` 目前是模块常量，
  如需运维可调再提升为配置项三件套）。
- **踩坑必须如实写**：`wait_for` 会取消 `anext` 把异步生成器杀死；「content 与 tool_calls 互斥」
  是被真实模型打破的假设；以及「同一进程内流式丢轨迹、非流式不丢」这个不对称现象是怎么定位的。

**Step 4: 提交**

```bash
git add OPTIMIZATION_PLAN.md
git commit -m "docs(plan): 流式三修入档——§12 待合并项与验收基线"
cd ../copilot-lite-private
git add -f docs/优化落地记录.md
git commit -m "docs: 流式链路三修落地记录——心跳截断/独白泄漏/新会话自杀"
```

---

## 交付物清单

- 后端：`api/routes/chat.py`、`agent/langgraph_engine.py`、`agent/orchestrator.py`、新建 `tests/test_chat_stream_heartbeat.py`、`tests/test_stream_no_narration.py`
- 前端：`components/ChatPanel.tsx`、`components/ChatPanel.test.tsx`
- 文档：`OPTIMIZATION_PLAN.md` §12、`private-docs/docs/优化落地记录.md`

## 不做（本次范围外）

- 不新增/改名 SSE 事件（含「撤回正文」事件）
- 不改 `Message.extra` 形状、不动轨迹词汇表
- 不把 `_STREAM_MAX_SECONDS` / `_HEARTBEAT_SECONDS` 提升为配置项（无三件套需求）
- 不改 supervisor 路由、不动工具白名单（Q2/Q4 仍冻结）
