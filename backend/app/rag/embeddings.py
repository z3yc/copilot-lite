"""嵌入服务：基于 fastembed（ONNX 本地推理）封装文本向量化。

选型理由（面试可讲）：
- DeepSeek 官方无 embedding API，需自备嵌入模型；
- fastembed 是 Qdrant 官方库，ONNX 运行时 ~50MB，远轻于 torch 方案；
- BGE-small-zh-v1.5：中文效果好、512 维、本地离线免费。

首次使用会自动下载模型（约 100MB）。国内网络默认走 hf-mirror 镜像
（用户已设置 HF_ENDPOINT 时以用户配置为准）；若下载异常可加
HF_HUB_DISABLE_XET=1 禁用 xet 协议（已默认设置）。
"""

import asyncio
import logging
import os
from functools import lru_cache

# 模型下载镜像与协议配置（setdefault：用户显式配置优先）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_DIMENSION = 512


class EmbeddingService:
    """文本向量化服务（线程池包装同步推理，避免阻塞事件循环）。"""

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None  # 懒加载

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            logger.info("加载嵌入模型: %s（首次使用自动下载）", self.model_name)
            self._model = TextEmbedding(model_name=self.model_name)
            logger.info("嵌入模型就绪")
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本列表 → 向量列表（异步非阻塞）。"""
        if not texts:
            return []
        model = self._load()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embed_sync, model, texts)

    def _embed_sync(self, model, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in model.embed(texts, batch_size=self.batch_size)]

    @property
    def dimension(self) -> int:
        return DEFAULT_DIMENSION


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """全局单例（模型只加载一次）。"""
    return EmbeddingService()
