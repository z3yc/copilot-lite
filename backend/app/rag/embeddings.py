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
import threading
from functools import lru_cache

from app.core.config import settings

# 模型下载镜像与协议配置（setdefault：用户显式配置优先）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
# Windows 默认无符号链接权限，禁用警告噪音
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_DIMENSION = 512


class EmbeddingService:
    """文本向量化服务（线程池包装同步推理，避免阻塞事件循环）。"""

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None  # 懒加载
        self._lock = threading.Lock()  # 防并发重复加载

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    logger.info("加载嵌入模型: %s（缓存目录: %s）", self.model_name, settings.EMBEDDING_CACHE_DIR)
                    try:
                        # 优先离线：缓存完整时秒级加载（否则每次联网校验/重试会卡 50s+）
                        self._model = TextEmbedding(
                            model_name=self.model_name,
                            cache_dir=settings.EMBEDDING_CACHE_DIR,
                            local_files_only=True,
                        )
                        logger.info("嵌入模型就绪（本地缓存命中，未联网）")
                    except Exception:  # noqa: BLE001  缓存未命中 → 联网下载（首次）
                        logger.info("本地缓存未命中，改为联网下载嵌入模型…")
                        self._model = TextEmbedding(
                            model_name=self.model_name,
                            cache_dir=settings.EMBEDDING_CACHE_DIR,
                        )
                        logger.info("嵌入模型就绪（已下载到 %s）", settings.EMBEDDING_CACHE_DIR)
        return self._model

    def prewarm(self) -> None:
        """预热模型（建议在线程池中调用）：触发一次加载/下载，避免首次请求卡顿。"""
        self._load()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本列表 → 向量列表（异步非阻塞）。

        单条文本（对话查询/记忆条目）走 lru_cache 查询缓存——
        查询向量重复率极高，缓存省下大量本地推理；批量摄取不走缓存。
        """
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        if len(texts) == 1:
            vec = await loop.run_in_executor(None, self._embed_one, texts[0])
            return [list(vec)]
        model = self._load()
        return await loop.run_in_executor(None, self._embed_sync, model, texts)

    @lru_cache(maxsize=settings.EMBED_QUERY_CACHE_SIZE)  # noqa: B019  服务为进程级单例，缓存随生命周期有效
    def _embed_one(self, text: str) -> tuple[float, ...]:
        """单条文本嵌入（lru_cache 缓存查询向量；线程安全）。

        注意：fastembed 的 `embed()` 返回**生成器**，不能下标访问（`[0]` 会报
        'generator' object is not subscriptable），必须用 next() 取首个。
        """
        model = self._load()
        vec = next(iter(model.embed([text])))
        return tuple(float(x) for x in vec)

    def _embed_sync(self, model, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in model.embed(texts, batch_size=self.batch_size)]

    @property
    def dimension(self) -> int:
        return DEFAULT_DIMENSION


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """全局单例（模型只加载一次）。"""
    return EmbeddingService()
