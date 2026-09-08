"""golden 评测集校验：确保结构合法、条目足够（CI 内不下载模型/不触网）。"""

import json
from pathlib import Path

_GOLDEN = Path(__file__).resolve().parents[1] / "eval" / "golden_set.json"


def test_golden_set_schema() -> None:
    """每条评测条目必须具备 query / expected_doc_title / must_contain。"""
    data = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    items = data.get("items", [])
    assert len(items) >= 5, "golden 集至少 5 条"

    for item in items:
        assert item.get("query"), f"缺 query: {item}"
        assert item.get("expected_doc_title"), f"缺 expected_doc_title: {item}"
        must = item.get("must_contain")
        assert isinstance(must, list) and must, f"must_contain 必填非空: {item}"
        # RAGAS 评测的参考答案（可选，提供时必须是字符串）
        gt = item.get("ground_truth")
        assert gt is None or isinstance(gt, str), f"ground_truth 必须是字符串: {item}"


def test_golden_set_has_ground_truth_for_ragas() -> None:
    """至少 5 条带参考答案，保证 RAGAS 评测脚本可用。"""
    data = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    with_gt = [i for i in data["items"] if i.get("ground_truth")]
    assert len(with_gt) >= 5, "RAGAS 评测需要至少 5 条带 ground_truth 的条目"


def test_golden_set_has_name_and_notes() -> None:
    """评测集需带名称与使用说明（面试展示的完整性）。"""
    data = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert data.get("name")
    assert data.get("说明")
