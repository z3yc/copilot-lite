"""大模型客户端封装：基于 DeepSeek（兼容 OpenAI SDK），支持 Function Calling。

设计要点：
- 对外暴露统一的 ChatResult 结构，屏蔽 SDK 差异；
- 工具调用（tool_calls）被解析为结构化对象，供编排器执行；
- API Key 从配置读取，缺失时给出清晰错误提示；
- 客户端为进程级单例（AsyncOpenAI 自带连接池，复用连接降低握手成本）；
- 超时/重试/max_tokens 显式配置（不依赖 SDK 默认值）；
- 进程内并发信号量：所有模型调用共享 LLM_MAX_CONCURRENCY 上限
  （含流式——流结束/异常时才释放，防止多个 SSE 同时打爆 API 限额）。
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# 并发信号量（懒创建：便于测试替换/按最新配置初始化）
_llm_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(max(1, settings.LLM_MAX_CONCURRENCY))
    return _llm_semaphore


class LLMError(Exception):
    """大模型调用失败（网络/限流/超时等），供上层映射为友好错误。"""


# ---------------- token 计量（进程内累计，供成本预算与监控） ----------------

_usage_stats: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _record_usage(usage) -> None:
    """把 SDK usage 对象/dict 累计进进程级统计。"""
    if usage is None:
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        if isinstance(value, int):
            _usage_stats[key] = _usage_stats.get(key, 0) + value


def get_usage_stats() -> dict[str, int]:
    """进程级累计用量快照（供预算与日志）。"""
    return dict(_usage_stats)


def reset_usage_stats() -> None:
    """测试用：清零累计统计。"""
    for key in _usage_stats:
        _usage_stats[key] = 0


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
    usage: dict | None = None  # {"prompt_tokens", "completion_tokens", "total_tokens"}

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class _GuardedStream:
    """包装流式响应：迭代结束（正常/异常/取消）时释放并发信号量。

    防止流式请求长期持有并发额度：消费完或中断即归还。
    """

    def __init__(self, stream, semaphore: asyncio.Semaphore) -> None:
        self._stream = stream
        self._sem = semaphore
        self._it: AsyncIterator | None = None
        self._released = False

    def __aiter__(self):
        self._it = self._stream.__aiter__()
        return self

    async def __anext__(self):
        assert self._it is not None
        try:
            chunk = await self._it.__anext__()
        except BaseException:
            self._release()
            raise
        # 流结束前的最后一个 chunk 携带 usage（include_usage 开启时）
        _record_usage(getattr(chunk, "usage", None))
        return chunk

    def _release(self) -> None:
        if not self._released:
            self._released = True
            self._sem.release()

    async def aclose(self) -> None:
        self._release()
        close = getattr(self._stream, "aclose", None)
        if close is not None:
            await close()


class LLMClient:
    """DeepSeek 聊天补全客户端。"""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        response_format: dict | None = None,
    ) -> ChatResult:
        """发起一次对话补全请求。

        messages: OpenAI 消息格式列表
        tools:    OpenAI tools 格式（Function Calling 定义）
        response_format: 结构化输出约束，如 {"type": "json_object"}；
                         兼容网关不支持时保持 None（仅靠 prompt 约束 + 容错解析）。
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if response_format:
            kwargs["response_format"] = response_format
        if settings.LLM_MAX_TOKENS:
            kwargs["max_tokens"] = settings.LLM_MAX_TOKENS

        async with _get_semaphore():
            resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        usage: dict | None = None
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
            _record_usage(usage)

        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                )

        return ChatResult(content=msg.content, tool_calls=tool_calls, usage=usage)

    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ):
        """流式对话补全：逐 token 产出内容增量（纯文本轮）。"""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if settings.LLM_MAX_TOKENS:
            kwargs["max_tokens"] = settings.LLM_MAX_TOKENS
        if settings.LLM_TRACK_STREAM_USAGE:
            kwargs["stream_options"] = {"include_usage": True}

        # 并发额度覆盖整个流生命周期（create + 逐 chunk 消费）
        sem = _get_semaphore()
        await sem.acquire()
        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                _record_usage(getattr(chunk, "usage", None))
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        finally:
            sem.release()

    async def stream_raw(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ):
        """原始流式响应：返回 chunk 迭代器，供编排器解析 content 与 tool_calls。

        用于 ReAct 流式循环：工具轮（content 为空）与纯文本轮（tool_calls 为空）
        在 DeepSeek 行为中互斥，可据此实时转发文本。
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if settings.LLM_MAX_TOKENS:
            kwargs["max_tokens"] = settings.LLM_MAX_TOKENS
        if settings.LLM_TRACK_STREAM_USAGE:
            kwargs["stream_options"] = {"include_usage": True}

        # 并发额度随流生命周期走：返回守卫迭代器，消费完/中断时自动释放
        sem = _get_semaphore()
        await sem.acquire()
        try:
            stream = await self._client.chat.completions.create(**kwargs)
        except BaseException:
            sem.release()
            raise
        return _GuardedStream(stream, sem)

    async def close(self) -> None:
        await self._client.close()


@lru_cache
def get_llm() -> LLMClient:
    """从配置创建 LLM 客户端（进程级单例，连接池复用）。"""
    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY：请在 backend/.env 中设置（参考 .env.example）"
        )
    return LLMClient(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_MODEL,
    )
