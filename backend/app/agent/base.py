"""Agent 抽象:为未来多智能体编排预留的扩展点(不写死架构)。

当前阶段:单一 Orchestrator(BaseAgent 的实现)完成"对话 + 工具调用"。
未来扩展方向(Post-MVP,见 README 路线图"后续规划"):

1. RouterAgent 意图路由:由路由 Agent 判断请求类型,分发给不同的子 Agent
   (例如 KnowledgeAgent / ToolAgent / MemoryAgent);
2. Agent-as-Tool 模式:子 Agent 通过工具协议暴露给其他 Agent 调用,
   复用现有 ToolRegistry(agent 本身就是工具,天然支持嵌套);
3. 若引入 LangGraph 类框架做状态机编排,BaseAgent 协议可平滑迁移。

所有 Agent 的统一契约:接收会话上下文与用户消息,返回回复文本。
"""

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


def estimate_tokens(text: str) -> int:
    """粗略 token 估算（仅用于上下文预算裁剪，不追求精确）。

    中文按字≈1 token；其余字符按 ~4 字符≈1 token（保守偏大）。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def _trim_by_tokens(convo: list[dict], max_tokens: int) -> list[dict]:
    """从末尾向前保留消息，直到估算 token 逼近预算（至少保留最后一条）。"""
    if max_tokens <= 0 or not convo:
        return convo
    kept: list[dict] = []
    total = 0
    for message in reversed(convo):
        cost = estimate_tokens(str(message.get("content") or "")) + 4  # +4 消息开销
        if kept and total + cost > max_tokens:
            break
        kept.append(message)
        total += cost
    return list(reversed(kept))


def split_system_context(
    history: list[dict], window: int, max_tokens: int | None = None
) -> tuple[list[dict], list[dict]]:
    """把固定注入的 system 上下文与滚动对话历史分开（双轨管理）。

    返回 (system_msgs, convo)：
    - system 上下文（附件/长期记忆等）常驻，不参与窗口截断，
      避免长对话把固定上下文“挤掉”；
    - 对话历史先按 window 拉条数，再按 max_tokens（缺省取配置
      HISTORY_MAX_TOKENS，0=不限）估算 token 裁剪，控制成本。
    """
    system_msgs = [m for m in history if m.get("role") == "system"]
    convo = [m for m in history if m.get("role") != "system"]
    budget = settings.HISTORY_MAX_TOKENS if max_tokens is None else max_tokens
    return system_msgs, _trim_by_tokens(convo[-window:], budget)


def confirmation_reply(pending: list[dict]) -> str:
    """构造“待用户确认”回复（human-in-the-loop）。"""
    lines = [
        f"- {p.get('name')}（参数：{p.get('arguments') or '{}'}）" for p in pending
    ]
    return (
        "以下操作需要你确认后才会执行：\n"
        + "\n".join(lines)
        + "\n\n请在界面上点击「确认执行」或「取消」。"
    )


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
        """执行一轮对话,返回助手回复。

        session:     数据库会话(供工具/记忆读写)
        user_id:     当前用户
        history:     历史消息 [{"role": ..., "content": ...}]
        user_message: 用户本轮输入
        """
        raise NotImplementedError
