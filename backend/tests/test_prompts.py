"""Prompt 资产管理测试：版本号 + 安全边界 + 模板变量（防迁移丢失）。"""

from app.core import prompts


def test_prompt_version_present():
    assert isinstance(prompts.PROMPT_VERSION, str)
    assert prompts.PROMPT_VERSION.strip()


def test_prompt_version_bumped_for_fund_notice():
    """新增基金行情文案后必须递增版本（AGENTS §18：变更可追溯/可灰度）。"""
    assert prompts.PROMPT_VERSION == "1.2.0"


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


def test_kb_prompts_mention_wiki():
    """知识库相关提示应明示 Wiki/维基，避免模型把它当成外部维基百科。"""
    for name in (
        "ORCHESTRATOR_SYSTEM_PROMPT",
        "SUPERVISOR_SYSTEM_PROMPT",
        "KB_SYSTEM_PROMPT",
    ):
        text = getattr(prompts, name)
        assert "Wiki" in text or "维基" in text, name


def test_keyword_route_recognizes_wiki():
    from app.agent.langgraph_engine import _keyword_route

    assert _keyword_route("调用wiki") == "kb"
    assert _keyword_route("查一下维基") == "kb"
