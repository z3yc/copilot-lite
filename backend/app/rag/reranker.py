"""Rerank 精排服务：基于 fastembed 交叉编码器（BAAI/bge-reranker-base）本地推理。

设计（面试可讲）：
- 混合检索（BM25 + 向量 + RRF）给出候选后，用**交叉编码器**对「query × passage」
  逐对打分——query 与 passage 深度交互，比双塔向量相似度更精准，但成本更高，
  所以只对 TopK 候选精排（检索 → 重排 → 生成 链路的中间环节）；
- 模型 BAAI/bge-reranker-base（fastembed ONNX 导出，本地离线免费）；
- 复用 hf-mirror 镜像 + 禁用 xet 协议（与 embeddings.py 一致，setdefault 不覆盖用户配置）；
- 同步 ONNX 推理通过 run_in_executor 线程池包装，不阻塞事件循环；
- 模型懒加载：单例首次调用才下载/加载（约 1GB），测试注入 Fake 不触网。

注：fastembed 0.8 的交叉编码器类名为 `TextCrossEncoder`
（`fastembed.TextReranking` 为更高版本的同能力入口，接口一致）。
"""

import asyncio
import logging
import os
from functools import lru_cache

# 模型下载镜像与协议配置（setdefault：用户显式配置优先）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-reranker-base"
DEFAULT_BATCH_SIZE = 32


class Reranker:
    """重排服务（线程池包装同步推理，避免阻塞事件循环）。

    对外只暴露 async rerank(query, passages, top_n)，返回按分数降序的
    (原索引, 分数) 列表——上层拿到索引即可重排候选，不感知模型细节。
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None  # 懒加载

    def _load(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            logger.info("加载重排模型: %s（首次使用自动下载）", self.model_name)
            self._model = TextCrossEncoder(model_name=self.model_name)
            logger.info("重排模型就绪")
        return self._model

    async def rerank(self, query: str, passages: list[str], top_n: int) -> list[tuple[int, float]]:
        """对候选段落精排，返回前 top_n 个 (原索引, 分数)，按分数降序。"""
        if not passages:
            return []
        if len(passages) == 1:
            return [(0, 1.0)]  # 唯一候选无需加载模型
        model = self._load()
        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(None, self._rerank_sync, model, query, passages)
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        return ranked[:top_n]

    def _rerank_sync(self, model, query: str, passages: list[str]) -> list[float]:
        return list(model.rerank(query, passages, batch_size=self.batch_size))


@lru_cache
def get_reranker() -> Reranker:
    """全局单例（模型只加载一次）。"""
    return Reranker()
