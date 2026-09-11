"""LangGraph 多 Agent 引擎：Supervisor 意图路由 + 三个子 Agent（知识库 / 工具 / 通用）。

设计（面试可讲）：
- **Supervisor 路由**：LLM 判断请求类型（JSON 输出），条件边分发到对应子 Agent；
  LLM 失败 / 格式异常时关键词兜底（工具 > 知识库 > 日常），保证路由不中断；
- **三个子 Agent**：复用同一套「工具调用循环」（bind_tools + ToolMessage 回填），
  各自系统提示限定能力边界：
  - 🧠 知识库 Agent：kb_search 检索 + 引用回答；
  - 🛠️ 工具 Agent：Todo 等全部工具；
  - 💬 通用 Agent：日常对话（无工具）；
- **工具复用**：ToolRegistry 条目转换为 langchain 工具定义（bind_tools），
  执行仍走 registry.execute（统一参数解析与错误兜底），不重复实现工具逻辑；
- **引擎并存**：与手写 ReAct 引擎（Orchestrator）通过 `AGENT_ENGINE` 配置切换，互不干扰；
- **流式**：graph.astream_events 过滤叶子节点的 on_chat_model_stream 事件，
  token 级输出，Supervisor 内部输出不泄漏给用户。
"""

import json
import logging
import re
from functools import lru_cache
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agent.base import BaseAgent, split_system_context
from app.core.config import settings
from app.core.json_parse import parse_json_object
from app.core.llm import LLMError
from app.tools.base import ToolContext, ToolRegistry
from app.tools.base import registry as global_registry

logger = logging.getLogger(__name__)

# 可选路由（与条件边 path_map 一一对应）
ROUTES = ("kb", "tools", "chat")

SUPERVISOR_SYSTEM_PROMPT = """你是 Copilot-Lite 的意图路由中枢。判断用户请求应交给哪个子 Agent，只输出一行 JSON：
{"route": "kb" | "tools" | "chat", "reason": "一句话理由"}

路由规则：
- kb（知识库）：问题涉及个人知识库 / 文档 / 笔记 / 资料（例如"我的笔记里…"、"根据文档…"）；
- tools（工具）：需要实际操作或管理，如待办（创建 / 查询 / 完成 / 删除）等；
- chat（日常对话）：寒暄、闲聊、通用问答、解释概念等。
只输出 JSON，不要输出任何其他内容。"""

KB_SYSTEM_PROMPT = """你是 Copilot-Lite 的知识库助手（青木）。回答用户问题时：
- 问题涉及知识库内容时，必须先调用 kb_search 检索，再基于检索结果回答；
- 回答注明来源（文档标题 / 章节 / 页码），引用时用 [n] 标注（n 为检索结果中的编号）；
- 检索不到相关内容时如实说明，不要编造。"""

TOOLS_SYSTEM_PROMPT = """你是 Copilot-Lite 的工具助手（青木）。当用户请求需要实际操作（如待办管理）时：
- 先想清楚参数，调用对应工具一次完成；
- 工具返回结果后用自然语言向用户汇报；
- 工具执行失败时如实告知，不要编造结果。"""

CHAT_SYSTEM_PROMPT = (
    """你是 Copilot-Lite（青木），一个个人专属助理。回答简洁、准确、友好，使用用户的语言。"""
)

# 各子 Agent 可用的工具（None = 全部工具）
AGENT_TOOLS: dict[str, list[str] | None] = {
    "kb_agent": ["kb_search"],
    "tools_agent": None,
    "chat_agent": [],
}

# 宽松匹配 LLM 输出中的 route 字段（容忍 ```json 围栏 / 多余文本）
_ROUTE_RE = re.compile(r'"route"\s*:\s*"(kb|tools|chat)"')


@lru_cache
def _get_langchain_llm() -> ChatOpenAI:
    """LangChain ChatOpenAI 进程级单例（连接池复用 + 显式超时/重试）。"""
    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY：请在 backend/.env 中设置（参考 .env.example）"
        )
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.7,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )

# 关键词兜底：工具优先于知识库（避免"创建/删除"等动作被知识库抢走）
_TOOL_KEYWORDS = ("待办", "todo", "创建", "完成", "删除", "提醒", "任务", "清单")
_KB_KEYWORDS = ("笔记", "文档", "知识库", "资料", "pdf", "文件", "检索")


class AgentState(TypedDict):
    """图状态（session/user_id 经引擎上下文注入，不入图，避免不可序列化对象）。"""

    history: list[dict]
    user_message: str
    route: str
    reply: str


def _parse_route(text: str) -> str | None:
    """从 Supervisor 输出中提取路由（JSON 解析优先，正则兜底）。"""
    if not text:
        return None
    data = parse_json_object(text)
    route = data.get("route")
    if isinstance(route, str) and route in ROUTES:
        return route
    match = _ROUTE_RE.search(text)
    return match.group(1) if match else None




def _keyword_route(user_message: str) -> str:
    """关键词兜底路由：工具 > 知识库 > 日常对话。"""
    msg = user_message.lower()
    if any(k in msg for k in _TOOL_KEYWORDS):
        return "tools"
    if any(k in msg for k in _KB_KEYWORDS):
        return "kb"
    return "chat"


def _to_langchain_messages(history: list[dict]) -> list:
    """历史消息 dict → langchain 消息对象（tool 角色等忽略）。"""
    out: list = []
    for m in history:
        role, content = m.get("role"), m.get("content") or ""
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        elif role == "system":
            out.append(SystemMessage(content=content))
    return out


class LangGraphEngine(BaseAgent):
    """LangGraph 多 Agent 引擎（Supervisor 路由 + 3 个子 Agent 节点 + 条件边）。"""

    def __init__(
        self,
        llm: ChatOpenAI | None = None,
        registry: ToolRegistry = global_registry,
        max_turns: int = settings.AGENT_MAX_TURNS,
    ) -> None:
        self.llm = llm if llm is not None else self._default_llm()
        self.registry = registry
        self.max_turns = max_turns
        # 本轮工具调用审计（run 后由上层写入 Message.extra 落库）
        self.last_tool_calls: list[dict] = []
        self._ctx: ToolContext | None = None  # 每次 run 注入（引擎按请求新建，无并发问题）
        self.graph = self._build_graph().compile()

    @staticmethod
    def _default_llm() -> ChatOpenAI:
        """DeepSeek（兼容 OpenAI 接口）的 langchain 客户端（进程级单例）。"""
        return _get_langchain_llm()

    # ---------- 图节点 ----------

    def _make_supervisor(self):
        """Supervisor 节点：LLM 意图判断（JSON），失败时关键词兜底。"""

        async def node(state: AgentState) -> dict:
            # Supervisor 只做意图路由：仅带滚动窗口内的对话历史（不含 system 注入）
            _, convo = split_system_context(state["history"], settings.HISTORY_WINDOW)
            messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)]
            messages.extend(_to_langchain_messages(convo))
            messages.append(HumanMessage(content=state["user_message"]))
            route = ""
            try:
                resp = await self.llm.ainvoke(messages)
                route = _parse_route(getattr(resp, "content", None) or "") or ""
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supervisor 意图判断失败，走关键词兜底: %s", exc)
            if route not in ROUTES:
                route = _keyword_route(state["user_message"])
            logger.info("路由: %s <- %s", route, state["user_message"][:20])
            return {"route": route}

        return node

    def _make_agent(self, node_name: str):
        """子 Agent 节点：系统提示限定能力边界 + 工具调用循环（至多 max_turns 轮）。"""
        system_prompt = {
            "kb_agent": KB_SYSTEM_PROMPT,
            "tools_agent": TOOLS_SYSTEM_PROMPT,
            "chat_agent": CHAT_SYSTEM_PROMPT,
        }[node_name]
        schemas = self._tool_schemas(AGENT_TOOLS[node_name])

        async def node(state: AgentState) -> dict:
            # system 上下文（附件/记忆）常驻 + 对话历史滚动窗口（与手写引擎同策略）
            system_msgs, convo = split_system_context(
                state["history"], settings.HISTORY_WINDOW
            )
            messages = [SystemMessage(content=system_prompt)]
            messages.extend(_to_langchain_messages(system_msgs))
            messages.extend(_to_langchain_messages(convo))
            messages.append(HumanMessage(content=state["user_message"]))
            bound = self.llm.bind_tools(schemas) if schemas else self.llm
            for _ in range(self.max_turns):
                try:
                    resp = await bound.ainvoke(messages)
                except Exception as exc:
                    logger.exception("子 Agent LLM 调用失败")
                    raise LLMError("模型服务暂时不可用") from exc
                if not resp.tool_calls:
                    return {"reply": resp.content or "（模型未返回内容）"}
                # 追加 assistant 工具调用声明，逐个执行并回填 ToolMessage
                messages.append(resp)
                for tc in resp.tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("args") or {}
                    logger.info("调用工具: %s(%s)", name, args)
                    result = await self.registry.execute(
                        name, json.dumps(args, ensure_ascii=False), self._ctx
                    )
                    self.last_tool_calls.append(
                        {
                            "name": name,
                            "arguments": json.dumps(args, ensure_ascii=False),
                            "result": str(result)[:500],
                        }
                    )
                    messages.append(ToolMessage(content=result, tool_call_id=tc.get("id", "")))
            return {"reply": "（已达到最大工具调用轮数，请简化请求后重试）"}

        return node

    def _tool_schemas(self, names: list[str] | None) -> list[dict]:
        """把 ToolRegistry 条目转换为 langchain 工具定义（OpenAI schema）。"""
        if names is None:
            names = self.registry.names()
        schemas = []
        for n in names:
            tool = self.registry.get(n)
            if tool:
                schemas.append(tool.to_openai_schema())
        return schemas

    # ---------- 图构建 ----------

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("supervisor", self._make_supervisor())
        graph.add_node("kb_agent", self._make_agent("kb_agent"))
        graph.add_node("tools_agent", self._make_agent("tools_agent"))
        graph.add_node("chat_agent", self._make_agent("chat_agent"))
        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            lambda state: state["route"],
            {"kb": "kb_agent", "tools": "tools_agent", "chat": "chat_agent"},
        )
        graph.add_edge("kb_agent", END)
        graph.add_edge("tools_agent", END)
        graph.add_edge("chat_agent", END)
        return graph

    # ---------- 运行协议（与 Orchestrator 一致：run / run_stream / close） ----------

    async def run(
        self,
        session,
        user_id,
        history: list[dict],
        user_message: str,
    ) -> str:
        """执行一次对话（图完整运行），返回最终回复。"""
        self._ctx = ToolContext(session=session, user_id=user_id)
        self.last_tool_calls = []
        state: AgentState = {
            "history": history,
            "user_message": user_message,
            "route": "",
            "reply": "",
        }
        result = await self.graph.ainvoke(state)
        return result.get("reply") or ""

    async def run_stream(self, session, user_id, history: list[dict], user_message: str):
        """流式执行：token 级产出最终回复（仅叶子 Agent 的模型输出）。"""
        self._ctx = ToolContext(session=session, user_id=user_id)
        self.last_tool_calls = []
        state: AgentState = {
            "history": history,
            "user_message": user_message,
            "route": "",
            "reply": "",
        }
        leaf_nodes = ("kb_agent", "tools_agent", "chat_agent")
        async for event in self.graph.astream_events(state, version="v2"):
            if event["event"] != "on_chat_model_stream":
                continue
            node = (event.get("metadata") or {}).get("langgraph_node")
            if node not in leaf_nodes:
                continue  # Supervisor 等内部输出不泄漏给用户
            chunk = event["data"].get("chunk")
            content = getattr(chunk, "content", None)
            if isinstance(content, str) and content:
                yield content

    async def close(self) -> None:
        """释放引擎资源。

        LLM 客户端为进程级单例（连接池复用），不再逐请求关闭，
        由应用生命周期统一管理。
        """
