"""RAG 检索评测脚本（golden set 评估）。

用法（在 backend 目录）：
    uv run python scripts/rag_eval.py                # 全量评测（默认 eval/golden_set.json）
    uv run python scripts/rag_eval.py --limit 5      # 只测前 5 条
    uv run python scripts/rag_eval.py --k 3          # recall@3 / MRR@3
    uv run python scripts/rag_eval.py --user-id <id> # 多用户模式按用户过滤检索

指标：
- recall@K：expected_doc_title 出现在前 K 条结果中的比例
- MRR：expected 命中排名的倒数均值（未命中记 0）

依赖：真实嵌入模型（首次运行自动下载 BGE-small-zh）与已摄取的知识库数据；
默认关闭 Rerank 精排以加快评测（RAG_RERANK_ENABLED=false），
需要对比时可手动开启（先在环境变量中设 RAG_RERANK_ENABLED=true 会优先采用）。
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# 默认关闭精排加速评测（用户显式设置则尊重）
os.environ.setdefault("RAG_RERANK_ENABLED", "false")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import async_session_factory
from app.rag import get_embedding_service, get_vector_store, hybrid_search

_GOLDEN_DEFAULT = Path(__file__).resolve().parents[1] / "eval" / "golden_set.json"


def _title_match(expected: str, hits) -> tuple[bool, int]:
    """expected 标题是否命中，命中时返回 (True, 排名从 1 起)。"""
    for rank, h in enumerate(hits, start=1):
        title = (h.meta or {}).get("document_title", "")
        if expected.lower() in title.lower():
            return True, rank
    return False, 0


async def evaluate(golden: dict, user_id: str | None, k: int, limit: int | None) -> dict:
    emb = get_embedding_service()
    store = get_vector_store()
    items = golden["items"][:limit] if limit else golden["items"]
    per_item: list[dict] = []
    found = 0
    mrr_sum = 0.0

    async with async_session_factory() as db:
        for item in items:
            hits = await hybrid_search(
                db, item["query"], emb, store, top_k=k, user_id=user_id
            )
            ok, rank = _title_match(item["expected_doc_title"], hits)
            mrr = 1.0 / rank if ok else 0.0
            found += int(ok)
            mrr_sum += mrr
            per_item.append(
                {
                    "query": item["query"],
                    "expected": item["expected_doc_title"],
                    "hit": ok,
                    "rank": rank or None,
                    "mrr": round(mrr, 4),
                    "top_titles": [(h.meta or {}).get("document_title", "") for h in hits[:k]],
                }
            )

    n = len(items) or 1
    return {
        "total": len(items),
        f"recall@{k}": round(found / n, 4),
        f"mrr@{k}": round(mrr_sum / n, 4),
        "items": per_item,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG golden set 检索评测")
    parser.add_argument("--golden", type=Path, default=_GOLDEN_DEFAULT, help="golden 集路径")
    parser.add_argument("--k", type=int, default=5, help="召回截断数（默认 5）")
    parser.add_argument("--limit", type=int, default=None, help="只测前 N 条")
    parser.add_argument("--user-id", type=str, default=None, help="多用户模式：检索用户 id")
    args = parser.parse_args()

    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    report = asyncio.run(evaluate(golden, args.user_id, args.k, args.limit))

    print(f"\n=== RAG 评测：{golden.get('name', args.golden.name)} ===")
    print(f"总数 {report['total']} · recall@{args.k} = {report[f'recall@{args.k}']} · "
          f"MRR@{args.k} = {report[f'mrr@{args.k}']}")
    print("\n--- 明细 ---")
    for item in report["items"]:
        mark = "✅" if item["hit"] else "❌"
        print(f"{mark} {item['query']} → 期望《{item['expected']}》 命中排名={item['rank']} "
              f"实际 top={item['top_titles']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
