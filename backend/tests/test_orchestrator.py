"""对话编排器（ReAct 循环）测试：使用 FakeLLM 模拟模型响应。"""

import pytest

from app.agent.orchestrator import Orchestrator
from app.core.constants import DEFAULT_USER_ID
from app.core.llm import ChatResult, ToolCall
from app.tools import registry


class FakeLLM:
    """按预设顺序返回响应的假模型。"""

    def __init__(self, responses: list[ChatResult]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    async def chat(self, messages, tools=None, temperature=0.7) -> ChatResult:
        self.requests.append({"messages": messages, "tools": tools})
        return self.responses.pop(0)

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_react_loop_with_tool_call(db_session) -> None:
    """模型先请求调用工具，拿到结果后再给出最终回复。"""
    fake = FakeLLM(
        [
            ChatResult(
                tool_calls=[
                    ToolCall(id="call_1", name="todo_create", arguments='{"title": "买菜"}')
                ]
            ),
            ChatResult(content="好的，已为你创建待办「买菜」"),
        ]
    )
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    reply = await orch.run(
        session=db_session,
        user_id=DEFAULT_USER_ID,
        history=[],
        user_message="帮我创建一个待办：买菜",
    )

    assert reply == "好的，已为你创建待办「买菜」"

    # 第一次请求应携带工具定义
    assert fake.requests[0]["tools"] is not None
    tool_names = [t["function"]["name"] for t in fake.requests[0]["tools"]]
    assert "todo_create" in tool_names

    # 第二轮请求中应包含 assistant tool_calls 与 tool 结果回填
    second = fake.requests[1]["messages"]
    roles = [m["role"] for m in second]
    assert "assistant" in roles and "tool" in roles


@pytest.mark.asyncio
async def test_direct_reply_without_tools(db_session) -> None:
    """无工具调用时直接返回文本。"""
    fake = FakeLLM([ChatResult(content="你好！有什么可以帮你？")])
    orch = Orchestrator(llm=fake, registry=registry, max_turns=3)

    reply = await orch.run(db_session, DEFAULT_USER_ID, [], "你好")
    assert reply == "你好！有什么可以帮你？"


@pytest.mark.asyncio
async def test_max_turns_guard(db_session) -> None:
    """模型持续请求工具时，达到最大轮数后终止。"""
    fake = FakeLLM(
        [
            ChatResult(tool_calls=[ToolCall(id=f"c{i}", name="todo_list", arguments="{}")])
            for i in range(10)
        ]
    )
    orch = Orchestrator(llm=fake, registry=registry, max_turns=2)
    reply = await orch.run(db_session, DEFAULT_USER_ID, [], "继续")
    assert "最大工具调用轮数" in reply
