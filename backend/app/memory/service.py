"""长期记忆服务：会话进行中节流提取 → 向量存储 → 混合召回。

流程：
1. 提取：会话后台任务按节流触发（新增 N 条消息一次），LLM 从对话中抽取
   稳定事实/偏好（结构化 JSON）；
2. 去重：新事实向量与已有记忆比对，相似度超阈值则跳过（避免重复累积）；
3. 存储：文本入 MEMORY_FACT 表，向量入 Qdrant memory 集合；
4. 召回：按当前问题向量检索 TopK 记忆，注入对话上下文。
"""

import json
import logging
import uuid
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_llm
from app.core.prompts.memory import MEMORY_EXTRACT_PROMPT
from app.models import MemoryFact
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "copilot_memories"
MEMORY_DIMENSION = 512
# 召回数量 / 去重相似度阈值 / 提取时参考的最近消息数
MEMORY_TOP_K = 5
DEDUP_THRESHOLD = 0.92
EXTRACT_WINDOW = 20


class MemoryService:
    """长期记忆的提取/存储/召回。"""

    def __init__(self, embeddings: EmbeddingService | None = None) -> None:
        self.embeddings = embeddings or get_embedding_service()
        self.vector_store = VectorStore(collection=MEMORY_COLLECTION, dimension=MEMORY_DIMENSION)

    # ---------- 提取 ----------

    async def extract_from_session(
        self,
        db: AsyncSession,
        user_id,
        session_id: uuid.UUID,
        messages: list[dict],
    ) -> int:
        """会话后台节流提取记忆（新增 N 条消息触发一次），返回新增条数。"""
        # 1. 组装最近消息供 LLM 提取
        recent = messages[-EXTRACT_WINDOW:]
        transcript = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}：{m['content'][:500]}"
            for m in recent
        )
        if not transcript.strip():
            return 0

        # 2. LLM 提取（失败静默，不影响主流程）
        try:
            llm = get_llm()
            result = await llm.chat(
                [
                    {"role": "system", "content": MEMORY_EXTRACT_PROMPT},
                    {"role": "user", "content": f"对话内容：\n{transcript}"},
                ]
            )
            facts = json.loads((result.content or "[]").strip())
            if not isinstance(facts, list):
                facts = []
        except Exception as exc:  # noqa: BLE001  记忆提取失败不应影响对话
            logger.warning("记忆提取失败: %s", exc)
            return 0

        # 3. 去重 + 入库
        added = 0
        for f in facts[:10]:
            fact = str(f.get("fact", "")).strip()
            if not fact or len(fact) > 300:
                continue
            if await self._is_duplicate(fact, user_id):
                continue
            await self._store(db, user_id, session_id, fact, f)
            added += 1
        if added:
            logger.info("提取记忆 %d 条（user=%s）", added, user_id)
        return added

    async def _is_duplicate(self, fact: str, user_id) -> bool:
        """向量相似度去重：与已有记忆最高分超阈值视为重复。

        仅在当前用户的记忆子空间内比较（多用户数据隔离——
        既防跨用户泄露，也防止被他人相似记忆误判重复而丢弃）。
        """
        try:
            vec = (await self.embeddings.embed([fact]))[0]
            hits = await self.vector_store.search(
                vec, top_k=1, user_id=str(user_id)
            )
            return bool(hits and hits[0].score >= DEDUP_THRESHOLD)
        except Exception:  # noqa: BLE001
            return False

    async def _store(self, db, user_id, session_id, fact: str, parsed: dict) -> None:
        category = str(parsed.get("category", "fact"))
        if category not in ("preference", "fact", "background"):
            category = "fact"
        confidence = float(parsed.get("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))

        row = MemoryFact(
            user_id=user_id,
            fact=fact,
            category=category,
            confidence=confidence,
            source_session_id=session_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        # 向量入库（payload 携带 id 便于删除同步；content 供检索解析）
        vec = (await self.embeddings.embed([fact]))[0]
        await self.vector_store.upsert(
            [
                (
                    row.id,
                    vec,
                    {
                        "memory_id": str(row.id),
                        "user_id": str(user_id),
                        "content": fact,
                        "category": category,
                    },
                )
            ]
        )

    # ---------- 召回 ----------

    async def recall(self, db: AsyncSession, user_id, query: str, top_k: int = MEMORY_TOP_K) -> list[str]:
        """按当前问题向量召回 TopK 记忆（供注入对话上下文）。

        仅召回当前用户的记忆（多用户数据隔离）。
        """
        try:
            vec = (await self.embeddings.embed([query]))[0]
            hits = await self.vector_store.search(vec, top_k=top_k, user_id=str(user_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("记忆召回失败: %s", exc)
            return []
        return [h.content for h in hits if h.content]

    # ---------- 删除 ----------

    async def delete(self, db: AsyncSession, user_id, memory_id: uuid.UUID) -> bool:
        """删除记忆（表 + 向量）。"""
        row = await db.get(MemoryFact, memory_id)
        if row is None or row.user_id != user_id:
            return False
        await db.delete(row)
        await db.commit()
        # 同步删除向量（按 memory_id 过滤）
        try:
            await self.vector_store.delete_by_memory(str(memory_id))
        except Exception as exc:  # noqa: BLE001  向量删除失败不影响表删除
            logger.warning("记忆向量删除失败: %s", exc)
        return True

    # ---------- 编辑 ----------

    async def update(
        self,
        db: AsyncSession,
        user_id,
        memory_id: uuid.UUID,
        fact: str,
        category: str = "fact",
    ) -> bool:
        """编辑记忆：修正事实内容与分类（同步更新向量）。"""
        row = await db.get(MemoryFact, memory_id)
        if row is None or row.user_id != user_id:
            return False
        row.fact = fact.strip()[:300]
        row.category = category if category in ("preference", "fact", "background") else "fact"
        await db.commit()

        # 更新向量（先删旧点，再写新向量）
        try:
            await self.vector_store.delete_by_memory(str(memory_id))
            vec = (await self.embeddings.embed([row.fact]))[0]
            await self.vector_store.upsert(
                [
                    (
                        row.id,
                        vec,
                        {
                            "memory_id": str(row.id),
                            "user_id": str(user_id),
                            "content": row.fact,
                            "category": row.category,
                        },
                    )
                ]
            )
        except Exception as exc:  # noqa: BLE001  向量更新失败不影响表更新
            logger.warning("记忆向量更新失败: %s", exc)
        return True


@lru_cache
def get_memory_service() -> MemoryService:
    return MemoryService()
