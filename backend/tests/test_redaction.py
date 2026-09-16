"""脱敏工具新家（core/redaction）：infra 层复用它，禁止反向依赖 app.agent。"""

from app.core.redaction import redact, redact_json_text


def test_redact_masks_nested_secret_values() -> None:
    out = redact({"env": {"FUND_API_KEY": "sk-real-secret"}, "retries": 3})
    assert out["env"]["FUND_API_KEY"] == "***"
    assert out["retries"] == 3


def test_redact_json_text_keeps_non_sensitive_untouched() -> None:
    raw = '{"max_tokens": 128, "refresh_token": "abc"}'
    assert "***" in redact_json_text(raw)
    assert redact_json_text('{"max_tokens": 128}') == '{"max_tokens": 128}'


def test_legacy_import_path_still_works() -> None:
    """旧路径（app.agent.trajectory）必须保持可用：既有调用方与测试不迁移。"""
    from app.agent.trajectory import redact_json_text as legacy

    assert legacy('{"token": "abc"}') == '{"token": "***"}'
