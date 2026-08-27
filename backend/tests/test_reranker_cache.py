"""Rerank 结果缓存测试：相同 (query, passages) 只推理一次。"""

import pytest

from app.rag.reranker import Reranker


class _CountingCrossEncoder:
    def __init__(self) -> None:
        self.calls = 0

    def rerank(self, query: str, documents, batch_size: int = 64):
        self.calls += 1
        return [len(doc) % 5 for doc in documents]


@pytest.mark.asyncio
async def test_rerank_results_cached() -> None:
    """相同 query+候选集命中缓存；不同候选集不命中；单候选短路不加载模型。"""
    r = Reranker(model_name="fake")
    model = _CountingCrossEncoder()
    r._model = model

    passages = ["段落一内容", "段落二内容比较长"]
    first = await r.rerank("问题", passages, top_n=2)
    second = await r.rerank("问题", passages, top_n=2)
    assert first == second
    assert model.calls == 1  # 第二次命中缓存

    await r.rerank("问题", ["段落一内容", "第三段"], top_n=2)
    assert model.calls == 2  # 候选集不同不命中
