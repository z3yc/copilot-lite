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
import threading
from functools import lru_cache

from app.core.config import settings

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
        self._lock = threading.Lock()  # 防并发重复加载

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    logger.info(
                        "加载重排模型: %s（缓存目录: %s）",
                        self.model_name,
                        settings.EMBEDDING_CACHE_DIR,
                    )
                    try:
                        # 离线优先：缓存完整时秒级加载（否则每次联网校验/重下会很慢）
                        self._model = TextCrossEncoder(
                            model_name=self.model_name,
                            cache_dir=settings.EMBEDDING_CACHE_DIR,
                            local_files_only=True,
                        )
                        logger.info("重排模型就绪（本地缓存命中，未联网）")
                    except Exception:  # noqa: BLE001  缓存未命中 → 联网下载（首次）
                        logger.info("重排模型本地缓存未命中，改为联网下载…")
                        self._model = TextCrossEncoder(
                            model_name=self.model_name,
                            cache_dir=settings.EMBEDDING_CACHE_DIR,
                        )
                        logger.info("重排模型就绪（已下载到 %s）", settings.EMBEDDING_CACHE_DIR)
        return self._model

    def prewarm(self) -> None:
        """预热模型（建议在线程池中调用）。"""
        self._load()

    async def rerank(self, query: str, passages: list[str], top_n: int) -> list[tuple[int, float]]:
        """对候选段落精排，返回前 top_n 个 (原索引, 分数)，按分数降序。

        结果按 (query, passages) 做 lru_cache——检索链路的候选集重复率较高，
        缓存可省下交叉编码器的重复推理；缓存键基于内容而非对象。
        """
        if not passages:
            return []
        if len(passages) == 1:
            return [(0, 1.0)]  # 唯一候选无需加载模型
        loop = asyncio.get_running_loop()
        ranked = await loop.run_in_executor(
            None, self._rerank_cached, query, tuple(passages), top_n
        )
        return list(ranked)

    @lru_cache(maxsize=settings.RERANK_CACHE_SIZE)  # noqa: B019  服务为进程级单例，缓存随生命周期有效
    def _rerank_cached(
        self, query: str, passages: tuple[str, ...], top_n: int
    ) -> tuple[tuple[int, float], ...]:
        """同步精排（线程池内执行；lru_cache 缓存，线程安全）。"""
        model = self._load()
        scores = model.rerank(query, list(passages), batch_size=self.batch_size)
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        return tuple((int(i), float(s)) for i, s in ranked[:top_n])


@lru_cache
def get_reranker() -> Reranker:
    """全局单例（模型只加载一次）。"""
    return Reranker()
