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

from app.agent.base import BaseAgent
from app.core.config import settings
from app.core.llm import LLMClient
from app.tools.base import ToolContext, ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 Copilot-Lite，一个个人专属 AI 智能助理。

行为准则：
- 回答简洁、准确、友好，使用用户的语言；
- 当用户请求涉及待办管理（创建/查询/完成/删除）时，必须调用对应工具完成任务；
- 调用工具前先想清楚参数，一次调用即可，不要重复调用；
- 工具返回结果后，用自然语言向用户汇报结果；
- 若工具不可用或执行失败，如实告知，不要编造结果。"""

# 短期记忆：单次上下文最多携带的历史消息条数
HISTORY_WINDOW = 20


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
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history[-HISTORY_WINDOW:])
        messages.append({"role": "user", "content": user_message})

        ctx = ToolContext(session=session, user_id=user_id)

        for _ in range(self.max_turns):
            result = await self.llm.chat(messages, tools=self.registry.schemas())

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
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": tool_result,
                    }
                )

        return "（已达到最大工具调用轮数，请简化请求后重试）"
