"""LLM 并发上限测试：信号量约束 + 流式守卫释放（异常路径）。"""

import asyncio
from types import SimpleNamespace

import pytest

import app.core.llm as llm_module
from app.core.llm import LLMClient, _GuardedStream


class _FakeCompletions:
    """模拟 chat.completions.create：统计并发峰值。"""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    async def create(self, **kwargs):
        self.current += 1
        self.peak = max(self.peak, self.current)
        try:
            await asyncio.sleep(0.05)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))
                ]
            )
        finally:
            self.current -= 1


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


@pytest.mark.asyncio
async def test_llm_concurrency_limited() -> None:
    """并发 5 个请求时，同时进行的模型调用不超过信号量上限。"""
    fake = _FakeClient()
    client = LLMClient(api_key="x", base_url="http://localhost:1", model="m")
    client._client = fake
    llm_module._llm_semaphore = asyncio.Semaphore(2)

    await asyncio.gather(
        *(client.chat([{"role": "user", "content": "hi"}]) for _ in range(5))
    )
    assert fake.chat.completions.peak <= 2


@pytest.mark.asyncio
async def test_guarded_stream_releases_on_exhaust() -> None:
    """守卫流：迭代耗尽后释放信号量。"""
    sem = asyncio.Semaphore(1)
    await sem.acquire()

    class _ChunkStream:
        def __init__(self) -> None:
            self._chunks = iter([SimpleNamespace(choices=[]), SimpleNamespace(choices=[])])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration:
                raise StopAsyncIteration from None

    guarded = _GuardedStream(_ChunkStream(), sem)
    async for _ in guarded:
        pass
    assert sem._value == 1  # 已释放


@pytest.mark.asyncio
async def test_guarded_stream_releases_on_error() -> None:
    """守卫流：迭代中途异常也释放信号量。"""
    sem = asyncio.Semaphore(1)
    await sem.acquire()

    class _BoomStream:
        def __init__(self) -> None:
            self._once = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._once:
                self._once = True
                return SimpleNamespace(choices=[])
            raise RuntimeError("boom")

    guarded = _GuardedStream(_BoomStream(), sem)
    with pytest.raises(RuntimeError):
        async for _ in guarded:
            pass
    assert sem._value == 1  # 异常路径也释放
