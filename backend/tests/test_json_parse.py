"""容错 JSON 解析测试（LLM 结构化输出）。"""

from app.core.json_parse import parse_json, parse_json_array, parse_json_object


def test_parse_plain_object():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    text = '```json\n{"route": "kb", "reason": "x"}\n```'
    assert parse_json_object(text) == {"route": "kb", "reason": "x"}


def test_parse_with_surrounding_noise():
    text = '好的，结果如下：{"title": "买菜", "priority": 3} 以上。'
    assert parse_json_object(text)["title"] == "买菜"


def test_parse_array_fenced():
    assert parse_json_array('```json\n["a", "b"]\n```') == ["a", "b"]


def test_parse_invalid_returns_default():
    assert parse_json("这不是 JSON", default=None) is None
    assert parse_json_object("这不是 JSON") == {}
    assert parse_json_array("这不是 JSON") == []


def test_parse_type_mismatch_falls_back():
    assert parse_json_object("[1, 2]") == {}
    assert parse_json_array('{"a": 1}') == []


def test_parse_empty_text():
    assert parse_json("") is None
    assert parse_json(None) is None
