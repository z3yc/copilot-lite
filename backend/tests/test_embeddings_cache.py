"""查询嵌入缓存测试：单条文本嵌入走 lru_cache，批量路径不走缓存。"""

import uuid

import numpy as np
import pytest

from app.core.config import settings
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


def test_prewarm_invokes_load(monkeypatch) -> None:
    """预热应触发一次模型加载（用于启动后台下载，避免首次请求卡顿）。"""
    svc = EmbeddingService()
    calls: list[int] = []
    monkeypatch.setattr(svc, "_load", lambda: calls.append(1))
    svc.prewarm()
    assert calls == [1]


def test_load_uses_configured_cache_dir(monkeypatch) -> None:
    """模型加载应使用 EMBEDDING_CACHE_DIR（固定持久卷，避免落 %TEMP% 被清理）。"""
    captured: dict = {}

    class _FakeTextEmbedding:
        def __init__(self, model_name=None, cache_dir=None, **kwargs):
            captured["model_name"] = model_name
            captured["cache_dir"] = cache_dir

    import fastembed

    monkeypatch.setattr(fastembed, "TextEmbedding", _FakeTextEmbedding)
    svc = EmbeddingService()
    svc._load()
    assert captured["cache_dir"] == settings.EMBEDDING_CACHE_DIR


def test_single_embed_handles_generator_model() -> None:
    """fastembed 的 embed() 返回生成器：单条路径不得下标访问（回归）。"""
    svc = EmbeddingService()

    class _GeneratorModel:
        def embed(self, texts, batch_size=None):
            for _ in texts:
                yield np.ones(8)

    svc._model = _GeneratorModel()
    text = f"生成器{uuid.uuid4().hex}"
    vec = svc._embed_one(text)
    assert len(vec) == 8
    assert all(v == 1.0 for v in vec)


@pytest.mark.asyncio
async def test_batch_embed_handles_generator_model() -> None:
    svc = EmbeddingService()

    class _GeneratorModel:
        def embed(self, texts, batch_size=None):
            for _ in texts:
                yield np.ones(8)

    svc._model = _GeneratorModel()
    out = await svc.embed([f"a{uuid.uuid4().hex}", f"b{uuid.uuid4().hex}"])
    assert len(out) == 2 and len(out[0]) == 8
