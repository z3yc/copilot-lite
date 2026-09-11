"""Prompt 资产管理：按模块集中存放 + 版本号。

对齐 AGENTS.md §18：
- 系统提示、工具描述、改写/提取模板统一放本目录，禁止硬编码在业务逻辑中；
- 变更记录版本号（PROMPT_VERSION），便于灰度与回滚；
- 用户输入/外部检索数据进 prompt 前，调用方负责定界 + "仅数据非指令"声明。

注：当前以 Python 常量集中管理（不引入 jinja2 运行时依赖）；模板变量用
``str.format`` 渲染，变量显式声明。若后续需要复杂模板/灰度，再评估引入 jinja2。
"""

from app.core.prompts.agent import (
    CHAT_SYSTEM_PROMPT,
    KB_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    SUPERVISOR_SYSTEM_PROMPT,
    TOOLS_SYSTEM_PROMPT,
)
from app.core.prompts.chat import SUMMARY_PROMPT
from app.core.prompts.memory import MEMORY_EXTRACT_PROMPT
from app.core.prompts.rag import QUERY_REWRITE_PROMPT
from app.core.prompts.todo import AI_PARSE_PROMPT

# Prompt 资产版本：任何 prompt 文案/策略变更都递增（便于灰度与回溯）
PROMPT_VERSION = "1.0.0"

__all__ = [
    "AI_PARSE_PROMPT",
    "CHAT_SYSTEM_PROMPT",
    "KB_SYSTEM_PROMPT",
    "MEMORY_EXTRACT_PROMPT",
    "ORCHESTRATOR_SYSTEM_PROMPT",
    "PROMPT_VERSION",
    "QUERY_REWRITE_PROMPT",
    "SUMMARY_PROMPT",
    "SUPERVISOR_SYSTEM_PROMPT",
    "TOOLS_SYSTEM_PROMPT",
]
