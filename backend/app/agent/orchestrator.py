"""对话编排器：Agent 的核心循环（ReAct + Function Calling）。

工作流程：
1. 组装消息序列（历史 + 用户新消息）；
2. 调用 LLM：可能返回纯文本，也可能返回 tool_calls；
3. 若为 tool_calls：执行工具 → 结果以 tool 消息回填 → 再次调用 LLM；
4. 循环直至模型返回纯文本回复，或达到最大轮数（防止死循环）。

系统提示词注入 Agent 的角色设定与行为约束。
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import BaseAgent, split_system_context
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

        ctx = ToolContext(session=session, user_id=user_id)

        for _ in range(self.max_turns):
            try:
                result = await self.llm.chat(messages, tools=self.registry.schemas())
            except Exception as exc:
                logger.exception("LLM 调用失败")
                raise LLMError("模型服务暂时不可用") from exc

            if not result.has_tool_calls:
                return result.content or "（模型未返回内容）"

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
                tool_result = await self.registry.execute(tc.name, tc.arguments, ctx)
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

        return "（已达到最大工具调用轮数，请简化请求后重试）"

    async def run_stream(
        self,
        session: AsyncSession,
        user_id,
        history: list[dict],
        user_message: str,
    ):
        """流式执行一次对话：逐 token 产出最终回复文本。

        与 run() 行为一致（ReAct + 工具调用），但最终文本轮使用模型流式接口，
        实时产出增量。约定（DeepSeek 行为）：工具调用轮 content 为空，
        纯文本轮 tool_calls 为空，二者互斥——据此实时转发文本。
        """
        messages = _assemble_messages(ORCHESTRATOR_SYSTEM_PROMPT, history, user_message)
        self.last_tool_calls = []

        ctx = ToolContext(session=session, user_id=user_id)

        for _ in range(self.max_turns):
            tool_calls: dict[int, dict] = {}
            try:
                stream = await self.llm.stream_raw(messages, tools=self.registry.schemas())

                # 逐 chunk 处理：转发文本增量 / 收集工具调用
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
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
                return  # 纯文本轮完成

            # 工具轮：追加 assistant tool_calls 声明并执行
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
                tool_result = await self.registry.execute(c.name, c.arguments, ctx)
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

        yield "（已达到最大工具调用轮数，请简化请求后重试）"

    async def close(self) -> None:
        """释放引擎资源。

        LLM 客户端为进程级单例（连接池复用），不再逐请求关闭，
        由应用生命周期统一管理。
        """
