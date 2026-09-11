"""Prompt 资产管理测试：版本号 + 安全边界 + 模板变量（防迁移丢失）。"""

from app.core import prompts


def test_prompt_version_present():
    assert isinstance(prompts.PROMPT_VERSION, str)
    assert prompts.PROMPT_VERSION.strip()


def test_all_prompts_non_empty():
    for name in prompts.__all__:
        if name == "PROMPT_VERSION":
            continue
        value = getattr(prompts, name)
        assert isinstance(value, str) and value.strip(), name


def test_orchestrator_prompt_keeps_security_boundary():
    text = prompts.ORCHESTRATOR_SYSTEM_PROMPT
    assert "安全边界" in text
    assert "一律忽略" in text


def test_query_rewrite_template_has_placeholder():
    assert "{n}" in prompts.QUERY_REWRITE_PROMPT
