"""查询改写：用户口语化问题 → 多路检索表述（multi-query 召回）。

为什么（面试可讲）：口语化问题与文档书面语之间存在"表达鸿沟"，
单一 query 召回有限；用 LLM 生成多个改写（同义改写/补全上下文/拆分子问题），
多路召回后跨查询 RRF 融合，明显提升召回率。
失败时静默回退原始问题（可用性优先，改写是锦上添花不是链路必需）。
"""

import json
import logging
from functools import lru_cache

from app.core.config import settings
from app.core.llm import LLMClient, get_llm
from app.core.prompts.rag import QUERY_REWRITE_PROMPT

logger = logging.getLogger(__name__)


class QueryRewriter:
    """LLM 查询改写器（失败静默回退，不阻塞检索链路）。"""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    async def rewrite(self, query: str) -> list[str]:
        """返回 [原问题, 改写1, ...]；任何失败（含无 Key/非法 JSON）都返回 [原问题]。"""
        variants = [query]
        n = max(1, settings.RAG_QUERY_REWRITE_VARIANTS)
        try:
            result = await self.llm.chat(
                [
                    {"role": "system", "content": QUERY_REWRITE_PROMPT.format(n=n)},
                    {"role": "user", "content": query},
                ]
            )
            parsed = json.loads((result.content or "[]").strip())
            if isinstance(parsed, list):
                seen = {query}
                for item in parsed:
                    text = str(item).strip()
                    if text and text not in seen:
                        seen.add(text)
                        variants.append(text)
                    if len(variants) > n:
                        break
        except Exception as exc:  # noqa: BLE001  改写失败不影响检索
            logger.warning("查询改写失败，回退原查询: %s", exc)
        return variants


@lru_cache
def get_rewriter() -> QueryRewriter:
    """进程级单例（LLM 客户端复用）。"""
    return QueryRewriter()
