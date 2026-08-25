"""向量存储：Qdrant 封装（本地模式，磁盘持久化，无需 Docker 服务器）。

设计：
- 本地模式 QdrantClient(path=...)，数据落在 backend/qdrant_data/（已 gitignore）；
- payload 携带 chunk 元数据（document_id / chunk_id / 标题路径 / 页码），
  支持过滤检索与引用溯源；
- 同步 SDK 通过 run_in_executor 包装，不阻塞事件循环。
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "copilot_chunks"


@dataclass
class SearchHit:
    """一次向量检索的命中结果。"""

    chunk_id: str
    document_id: str
    content: str
    score: float
    meta: dict


class VectorStore:
    """Qdrant 向量库封装。"""

    def __init__(self, collection: str = COLLECTION_NAME, dimension: int = 512) -> None:
        self.collection = collection
        # 本地模式（path）优先；配置了远程 URL 时使用远程（云端部署）
        if settings.QDRANT_URL and not settings.QDRANT_URL.startswith("http://localhost:6333"):
            self._client = QdrantClient(url=settings.QDRANT_URL)
            logger.info("Qdrant 远程模式: %s", settings.QDRANT_URL)
        else:
            self._client = QdrantClient(path=settings.QDRANT_PATH)
            logger.info("Qdrant 本地模式: %s", settings.QDRANT_PATH)
        self._ensure_collection(dimension)

    def _ensure_collection(self, dimension: int = 512) -> None:
        if not self._client.collection_exists(self.collection):
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
            )
            logger.info("已创建向量集合: %s (dim=%s)", self.collection, dimension)

    async def upsert(
        self,
        points: list[tuple[uuid.UUID, list[float], dict]],
    ) -> None:
        """批量写入向量点：(chunk_id, vector, payload)。"""
        if not points:
            return
        qm_points = [
            qm.PointStruct(id=str(cid), vector=vector, payload=payload)
            for cid, vector, payload in points
        ]
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._client.upsert, self.collection, qm_points
        )

    async def search(self, vector: list[float], top_k: int, document_id: str | None = None) -> list[SearchHit]:
        """向量相似度检索，可限定文档范围。"""
        qfilter = None
        if document_id:
            qfilter = qm.Filter(
                must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))]
            )
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=top_k,
                query_filter=qfilter,
                with_payload=True,
            ),
        )
        return [
            SearchHit(
                chunk_id=h.payload.get("chunk_id", ""),
                document_id=h.payload.get("document_id", ""),
                content=h.payload.get("content", ""),
                score=h.score,
                meta=h.payload.get("meta", {}),
            )
            for h in resp.points
        ]

    async def delete_by_document(self, document_id: uuid.UUID) -> None:
        """删除某文档的全部向量点。"""
        qfilter = qm.Filter(
            must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=str(document_id)))]
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete(
                self.collection, points_selector=qm.FilterSelector(filter=qfilter)
            ),
        )


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
