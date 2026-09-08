"""RAGAS 生成质量评测脚本（faithfulness / context / response 指标）。

用法（在 backend 目录，需已配置 DEEPSEEK_API_KEY 与已摄取的知识库数据）：
    uv run python scripts/rag_eval_ragas.py                # 全量
    uv run python scripts/rag_eval_ragas.py --limit 5      # 只测前 5 条
    uv run python scripts/rag_eval_ragas.py --top-k 3      # 检索截断数

流程：golden 集问题 → 混合检索取上下文 → DeepSeek 生成答案 → RAGAS 打分。
指标：
- Faithfulness       答案是否忠实于检索内容（有无幻觉）
- ContextRelevance   检索内容与问题的相关度
- ResponseRelevancy  回答与问题的相关度

说明：
1) ragas 0.3.1 与 langchain-community 1.x 存在兼容缺口——ragas 无条件导入已被移除的
   chat_models.vertexai 模块；脚本顶部注册占位模块绕开（本项目不使用 VertexAI）。
2) 每个指标每次打分都是一次 LLM 调用（DeepSeek 作 judge），注意评测成本。
"""

import argparse
import asyncio
import json
import os
import sys
import types
from pathlib import Path

# ---- ragas 兼容占位（见模块 docstring 说明 1） ----
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _stub = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:  # pragma: no cover - 占位类，不被本项目使用
        ...

    _stub.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = _stub

# 评测默认关精排加速检索（用户显式设置则尊重）
os.environ.setdefault("RAG_RERANK_ENABLED", "false")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.embeddings import Embeddings
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    ContextRelevance,
    Faithfulness,
    ResponseRelevancy,
)

from app.agent.langgraph_engine import _get_langchain_llm
from app.core.db import async_session_factory
from app.rag import get_embedding_service, get_vector_store, hybrid_search

_GOLDEN_DEFAULT = Path(__file__).resolve().parents[1] / "eval" / "golden_set.json"


class LocalEmbeddings(Embeddings):
    """fastembed 本地模型的 langchain Embeddings 适配（供 ragas 指标计算）。"""

    def __init__(self) -> None:
        self._svc = get_embedding_service()
        self._model = self._svc._load()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self._model.embed([text])[0].tolist()


async def _generate_answer(llm, question: str, contexts: list[str]) -> str:
    """DeepSeek 基于检索上下文生成回答（与线上知识库助手同风格）。"""
    ctx_block = "\n\n".join(f"[{i + 1}] {c[:800]}" for i, c in enumerate(contexts[:5]))
    prompt = (
        "你是知识库助手。请基于以下检索内容回答用户问题，引用时用 [n] 标注编号；"
        "检索内容不足时如实说明。\n\n"
        f"检索内容：\n{ctx_block}\n\n"
        f"用户问题：{question}"
    )
    resp = await llm.ainvoke(prompt)
    return str(resp.content)


async def evaluate_ragas(golden: dict, limit: int | None, top_k: int) -> dict:
    llm = _get_langchain_llm()
    wrapper_llm = LangchainLLMWrapper(llm)
    wrapper_emb = LangchainEmbeddingsWrapper(LocalEmbeddings())
    metrics = [
        Faithfulness(llm=wrapper_llm),
        ContextRelevance(llm=wrapper_llm, embeddings=wrapper_emb),
        ResponseRelevancy(llm=wrapper_llm, embeddings=wrapper_emb),
    ]

    samples: list[SingleTurnSample] = []
    records: list[dict] = []
    emb = get_embedding_service()
    store = get_vector_store()
    items = golden["items"][:limit] if limit else golden["items"]

    async with async_session_factory() as db:
        for item in items:
            hits = await hybrid_search(db, item["query"], emb, store, top_k=top_k)
            contexts = [h.content for h in hits]
            answer = await _generate_answer(llm, item["query"], contexts)
            samples.append(
                SingleTurnSample(
                    question=item["query"],
                    contexts=contexts,
                    answer=answer,
                    reference=str(item.get("ground_truth") or ""),
                )
            )
            records.append(
                {"query": item["query"], "answer": answer, "contexts": contexts[:3]}
            )

    dataset = EvaluationDataset(samples=samples)
    result = evaluate(dataset=dataset, metrics=metrics)
    df = result.to_pandas()
    numeric = df.select_dtypes(include="number")
    scores = [
        {"metric": str(col), "mean": round(float(numeric[col].mean()), 4)}
        for col in numeric.columns
    ]
    return {"rows": records, "scores": scores}


def main() -> int:
    parser = argparse.ArgumentParser(description="RAGAS 生成质量评测")
    parser.add_argument("--golden", type=Path, default=_GOLDEN_DEFAULT, help="golden 集路径")
    parser.add_argument("--limit", type=int, default=None, help="只测前 N 条")
    parser.add_argument("--top-k", type=int, default=5, help="检索截断数（默认 5）")
    args = parser.parse_args()

    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    report = asyncio.run(evaluate_ragas(golden, args.limit, args.top_k))

    print(f"\n=== RAGAS 评测：{golden.get('name', args.golden.name)} ===")
    for s in report["scores"]:
        print(f"  {s['metric']}: {s['mean']}")
    print(f"\n--- 明细（共 {len(report['rows'])} 条）---")
    for r in report["rows"]:
        print(f"Q: {r['query']}\nA: {r['answer'][:120]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
