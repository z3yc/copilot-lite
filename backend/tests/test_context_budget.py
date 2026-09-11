"""上下文 token 预算测试：估算、双轨裁剪、边界。"""

from app.agent.base import estimate_tokens, split_system_context


def test_estimate_tokens_basic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2


def test_split_keeps_system_and_trims_by_tokens():
    history = [
        {"role": "system", "content": "固定上下文"},
        {"role": "user", "content": "a" * 100},
        {"role": "assistant", "content": "b" * 100},
        {"role": "user", "content": "最近"},
    ]
    system_msgs, convo = split_system_context(history, window=10, max_tokens=30)
    assert system_msgs == [{"role": "system", "content": "固定上下文"}]
    assert convo[-1]["content"] == "最近"
    # 100 字符 ≈ 25 token + 开销，超出 30 预算 → 被裁掉
    assert all(m["role"] != "system" for m in convo)
    assert len(convo) == 1


def test_token_budget_zero_means_unlimited():
    history = [{"role": "user", "content": "x" * 1000}]
    _, convo = split_system_context(history, window=10, max_tokens=0)
    assert len(convo) == 1


def test_keeps_at_least_last_message_over_budget():
    history = [{"role": "user", "content": "x" * 10000}]
    _, convo = split_system_context(history, window=10, max_tokens=5)
    assert len(convo) == 1
