"""对话编排器：Agent 的核心循环（ReAct + Function Calling）。

工作流程：
1. 组装消息序列（历史 + 用户新消息）；
2. 调用 LLM：可能返回纯文本，也可能返回 tool_calls；
3. 若为 tool_calls：执行工具 → 结果以 tool 消息回填 → 再次调用 LLM；
4. 循环直至模型返回纯文本回复，或达到最大轮数（防止死循环）。

系统提示词注入 Agent 的角色设定与行为约束。
"""

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import BaseAgent, confirmation_reply, split_system_context
from app.agent.trajectory import TrajectoryRecorder, elapsed_ms
from app.core.config import settings
from app.core.llm import LLMClient, LLMError, ToolCall
from app.core.prompts import ORCHESTRATOR_SYSTEM_PROMPT
from app.tools.base import ToolContext, ToolRegistry

logger = logging.getLogger(__name__)


def _assemble_messages(
    system_prompt: str, history: list[dict], user_message: str
) -> list[dict]:
    """组装消息序列：系统提示 + 常驻 system 上下文（附件/记忆）+ 滚动窗口历史 + 新消息。

    system 上下文与对话历史双轨管理：system 部分不参与窗口截断，
    对话历史按 settings.HISTORY_WINDOW 滚动（长对话不丢固定上下文，也不超窗）。
    """
    system_msgs, convo = split_system_context(history, settings.HISTORY_WINDOW)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(system_msgs)
    messages.extend(convo)
    messages.append({"role": "user", "content": user_message})
    return messages


class Orchestrator(BaseAgent):
    """编排一次多轮对话（含工具调用）。

    当前为单 Agent 实现；未来多智能体场景下，本类可演化为
    "工具型子 Agent"，由 RouterAgent 统一调度（见 base.py 扩展说明）。
    """

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        max_turns: int = settings.AGENT_MAX_TURNS,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.max_turns = max_turns
        # 本轮工具调用审计（run 后由上层写入 Message.extra 落库）
        self.last_tool_calls: list[dict] = []
        # 需用户确认的挂起操作（human-in-the-loop）
        self.pending_confirmation: list[dict] = []
        # 本轮检索引用（供上层落 Message.extra.citations）
        self.last_citations: list[dict] = []
        # 本轮轨迹（node/tool/answer）：run 后由上层写入 Message.extra
        self.trace = TrajectoryRecorder("handwritten", enabled=settings.AGENT_TRACE_ENABLED)
        # 轨迹规范化结果（run/run_stream 收尾时写入；开关关闭时为空 dict）
        self.last_trajectory: dict = {}

    def _seal_trajectory(self, chars: int) -> None:
        """轨迹收尾：记录回复长度并规范化（run/run_stream 的每个出口都要调用）。"""
        self.trace.answer(chars)
        self.last_trajectory = self.trace.build()

    def _start_trajectory(self) -> None:
        """轨迹开场：重置并记录节点（手写引擎只有一个执行节点，无路由）。"""
        self.trace.reset()
        self.trace.node("orchestrator")

    async def run(
        self,
        session: AsyncSession,
        user_id,
        history: list[dict],
        user_message: str,
    ) -> str:
        """执行一次对话，返回最终回复。

        history: 历史消息列表，元素为 {"role": ..., "content": ...}
        """
        messages = _assemble_messages(ORCHESTRATOR_SYSTEM_PROMPT, history, user_message)
        self.last_tool_calls = []
        self.pending_confirmation = []
        self.last_citations = []
        self._start_trajectory()

        ctx = ToolContext(session=session, user_id=user_id)

        for _ in range(self.max_turns):
            try:
                result = await self.llm.chat(messages, tools=self.registry.schemas())
            except Exception as exc:
                logger.exception("LLM 调用失败")
                raise LLMError("模型服务暂时不可用") from exc

            if not result.has_tool_calls:
                self.last_citations = list(ctx.citations)
                reply = result.content or "（模型未返回内容）"
                self._seal_trajectory(len(reply))
                return reply

            # 追加 assistant 的工具调用声明（OpenAI 协议要求）
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in result.tool_calls
                    ],
                }
            )
            # 逐个执行工具并把结果回填
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
                        tc.name,
                        tc.arguments,
                        tool_result,
                        status="pending_confirmation",
                        ms=elapsed_ms(started),
                    )
                else:
                    tool_result = await self.registry.execute(tc.name, tc.arguments, ctx)
                    self.trace.tool(
                        tc.name,
                        tc.arguments,
                        tool_result,
                        status="ok",
                        ms=elapsed_ms(started),
                    )
                    self.last_tool_calls.append(
                        {
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": tool_result[:500],
                        }
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": tool_result,
                    }
                )
            if self.pending_confirmation:
                self.last_citations = list(ctx.citations)
                reply = confirmation_reply(self.pending_confirmation)
                self._seal_trajectory(len(reply))
                return reply

        self.last_citations = list(ctx.citations)
        reply = "（已达到最大工具调用轮数，请简化请求后重试）"
        self._seal_trajectory(len(reply))
        return reply

    async def run_stream(
        self,
        session: AsyncSession,
        user_id,
        history: list[dict],
        user_message: str,
    ):
        """流式执行一次对话：产出最终回复文本（**按模型轮**，不是逐 token）。

        与 run() 行为一致（ReAct + 工具调用）。因每一轮都可能调用工具、无法预判
        当前轮是否已是回答轮，所以文本按**模型轮**缓冲：带 tool_calls 的轮次其
        content 是模型独白（如 "I'll check your todo list for you."），一律丢弃；
        只有本轮没有任何 tool_calls 时才把缓冲的文本作为回答产出——用户看到的是
        逐轮（整段）产出，而非逐 token 流式。
        """
        messages = _assemble_messages(ORCHESTRATOR_SYSTEM_PROMPT, history, user_message)
        self.last_tool_calls = []
        self.pending_confirmation = []
        self.last_citations = []
        self._start_trajectory()

        ctx = ToolContext(session=session, user_id=user_id)

        chars = 0
        for _ in range(self.max_turns):
            tool_calls: dict[int, dict] = {}
            round_parts: list[str] = []
            try:
                stream = await self.llm.stream_raw(messages, tools=self.registry.schemas())

                # 逐 chunk 处理：本轮文本先入缓冲，tool_calls 边收边拼
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        round_parts.append(delta.content)
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            entry = tool_calls.setdefault(
                                tc.index, {"id": tc.id or "", "name": "", "arguments": ""}
                            )
                            if tc.id:
                                entry["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    entry["name"] += tc.function.name
                                if tc.function.arguments:
                                    entry["arguments"] += tc.function.arguments
            except Exception as exc:
                logger.exception("LLM 流式调用失败")
                raise LLMError("模型服务暂时不可用") from exc

            if not tool_calls:
                # 纯文本轮：本轮缓冲即回答（工具轮的独白在此前已被丢弃）
                self.last_citations = list(ctx.citations)
                text = "".join(round_parts)
                chars += len(text)
                self._seal_trajectory(chars)
                if text:
                    yield text
                return

            # 工具轮：本轮的 content 是独白，不产出（round_parts 直接丢弃）
            calls = [
                ToolCall(id=e["id"], name=e["name"], arguments=e["arguments"])
                for e in tool_calls.values()
            ]
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in calls
                    ],
                }
            )
            for c in calls:
                logger.info("调用工具: %s(%s)", c.name, c.arguments)
                started = time.perf_counter()
                if self.registry.is_confirmation_required(c.name):
                    self.pending_confirmation.append(
                        {"name": c.name, "arguments": c.arguments, "tool_call_id": c.id}
                    )
                    tool_result = "（该操作需用户确认，已挂起，尚未执行）"
                    self.trace.tool(
                        c.name,
                        c.arguments,
                        tool_result,
                        status="pending_confirmation",
                        ms=elapsed_ms(started),
                    )
                else:
                    tool_result = await self.registry.execute(c.name, c.arguments, ctx)
                    self.trace.tool(
                        c.name,
                        c.arguments,
                        tool_result,
                        status="ok",
                        ms=elapsed_ms(started),
                    )
                    self.last_tool_calls.append(
                        {
                            "name": c.name,
                            "arguments": c.arguments,
                            "result": tool_result[:500],
                        }
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.id,
                        "name": c.name,
                        "content": tool_result,
                    }
                )
            if self.pending_confirmation:
                self.last_citations = list(ctx.citations)
                text = confirmation_reply(self.pending_confirmation)
                chars += len(text)
                self._seal_trajectory(chars)
                yield text
                return

        self.last_citations = list(ctx.citations)
        text = "（已达到最大工具调用轮数，请简化请求后重试）"
        chars += len(text)
        self._seal_trajectory(chars)
        yield text

    async def close(self) -> None:
        """释放引擎资源。

        LLM 客户端为进程级单例（连接池复用），不再逐请求关闭，
        由应用生命周期统一管理。
        """
