"""大模型客户端封装：基于 DeepSeek（兼容 OpenAI SDK），支持 Function Calling。

设计要点：
- 对外暴露统一的 ChatResult 结构，屏蔽 SDK 差异；
- 工具调用（tool_calls）被解析为结构化对象，供编排器执行；
- API Key 从配置读取，缺失时给出清晰错误提示。
"""

import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """模型请求调用某个工具。"""

    id: str
    name: str
    arguments: str  # JSON 字符串


@dataclass
class ChatResult:
    """一次模型响应的统一结果。"""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMClient:
    """DeepSeek 聊天补全客户端。"""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> ChatResult:
        """发起一次对话补全请求。

        messages: OpenAI 消息格式列表
        tools:    OpenAI tools 格式（Function Calling 定义）
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                )

        return ChatResult(content=msg.content, tool_calls=tool_calls)

    async def close(self) -> None:
        await self._client.close()


def get_llm() -> LLMClient:
    """从配置创建 LLM 客户端（单例缓存）。"""
    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY：请在 backend/.env 中设置（参考 .env.example）"
        )
    return LLMClient(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_MODEL,
    )
