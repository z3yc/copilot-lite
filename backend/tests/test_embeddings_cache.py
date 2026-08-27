"""查询嵌入缓存测试：单条文本嵌入走 lru_cache，批量路径不走缓存。"""

import uuid

import numpy as np
import pytest

from app.rag.embeddings import EmbeddingService


class _CountingModel:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts, batch_size=None):
        self.calls += 1
        return [np.full(8, 0.5) for _ in texts]


@pytest.mark.asyncio
async def test_single_query_embedding_cached() -> None:
    """相同单条文本只推理一次（命中 lru_cache）；批量摄取不缓存。"""
    svc = EmbeddingService()
    model = _CountingModel()
    svc._model = model  # 直接注入，避免下载真实模型

    text = f"查询{uuid.uuid4().hex}"
    v1 = await svc.embed([text])
    v2 = await svc.embed([text])
    assert v1 == v2
    assert model.calls == 1  # 第二次命中缓存

    await svc.embed(["另一个问题"])
    assert model.calls == 2

    await svc.embed(["批量甲", "批量乙"])
    assert model.calls == 3  # 批量路径不缓存
