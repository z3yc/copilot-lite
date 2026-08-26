"""Agent 核心：对话编排、记忆、工具调度。

- BaseAgent：Agent 抽象协议（所有引擎的统一契约）
- Orchestrator：手写 ReAct 引擎（单 Agent，Function Calling）
- LangGraphEngine：LangGraph 多 Agent 引擎（Supervisor 路由 + 3 子 Agent，默认）
"""

from app.agent.base import BaseAgent
from app.agent.langgraph_engine import LangGraphEngine
from app.agent.orchestrator import Orchestrator

__all__ = ["BaseAgent", "LangGraphEngine", "Orchestrator"]
