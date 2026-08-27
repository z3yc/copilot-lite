"""Agent 抽象：为未来多智能体编排预留的扩展点（不写死架构）。

当前阶段：单一 Orchestrator（BaseAgent 的实现）完成"对话 + 工具调用"。
未来扩展方向（Post-MVP，见 README 路线图"后续规划"）：

1. RouterAgent 意图路由：由路由 Agent 判断请求类型，分发给不同的子 Agent
   （例如 KnowledgeAgent / ToolAgent / MemoryAgent）；
2. Agent-as-Tool 模式：子 Agent 通过工具协议暴露给其他 Agent 调用，
   复用现有 ToolRegistry（agent 本身就是工具，天然支持嵌套）；
3. 若引入 LangGraph 类框架做状态机编排，BaseAgent 协议可平滑迁移。

所有 Agent 的统一契约：接收会话上下文与用户消息，返回回复文本。
"""

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


def split_system_context(
    history: list[dict], window: int
) -> tuple[list[dict], list[dict]]:
    """把固定注入的 system 上下文与滚动对话历史分开（双轨管理）。

    返回 (system_msgs, convo[-window:])：
    - system 上下文（附件/长期记忆等）常驻，不参与窗口截断，
      避免长对话把固定上下文"挤掉"；
    - 对话历史按 window 滚动截断，控制 token 成本。
    """
    system_msgs = [m for m in history if m.get("role") == "system"]
    convo = [m for m in history if m.get("role") != "system"]
    return system_msgs, convo[-window:]


class BaseAgent(ABC):
    """所有 Agent 的公共协议。"""

    @abstractmethod
    async def run(
        self,
        session: AsyncSession,
        user_id,
        history: list[dict],
        user_message: str,
    ) -> str:
        """执行一轮对话，返回助手回复。

        session:     数据库会话（供工具/记忆读写）
        user_id:     当前用户
        history:     历史消息 [{"role": ..., "content": ...}]
        user_message: 用户本轮输入
        """
        raise NotImplementedError
