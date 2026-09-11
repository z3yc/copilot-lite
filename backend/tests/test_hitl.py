"""Human-in-the-loop 测试：危险工具挂起、确认/取消执行。"""

import json
from typing import ClassVar

from httpx import ASGITransport, AsyncClient

from app.agent.orchestrator import Orchestrator
from app.core.llm import ChatResult, ToolCall
from app.main import app
from app.tools import registry as global_registry
from app.tools.base import ToolRegistry


def test_registry_confirmation_flag():
    assert global_registry.is_confirmation_required("todo_delete") is True
    assert global_registry.is_confirmation_required("todo_list") is False
    assert global_registry.is_confirmation_required("not_exist") is False


async def test_orchestrator_gates_dangerous_tool():
    reg = ToolRegistry()
    executed: list[str] = []

    @reg.register(requires_confirmation=True)
    async def danger(ctx, x: str = "y") -> str:
        """危险工具"""
        executed.append(x)
        return "done"

    class OneShotLLM:
        async def chat(self, messages, tools=None, temperature=0.7, response_format=None):
            return ChatResult(
                content=None,
                tool_calls=[ToolCall(id="1", name="danger", arguments='{"x": "v"}')],
            )

    agent = Orchestrator(llm=OneShotLLM(), registry=reg)
    reply = await agent.run(None, "u1", [], "执行危险操作")
    assert "确认" in reply
    assert executed == []  # 未被真正执行
    assert agent.pending_confirmation[0]["name"] == "danger"


async def test_orchestrator_executes_safe_tool():
    reg = ToolRegistry()
    executed: list[str] = []

    @reg.register
    async def safe(ctx) -> str:
        """安全工具"""
        executed.append("yes")
        return "ok"

    class TwoShotLLM:
        def __init__(self) -> None:
            self.n = 0

        async def chat(self, messages, tools=None, temperature=0.7, response_format=None):
            self.n += 1
            if self.n == 1:
                return ChatResult(
                    content=None, tool_calls=[ToolCall(id="1", name="safe", arguments="{}")]
                )
            return ChatResult(content="完成")

    agent = Orchestrator(llm=TwoShotLLM(), registry=reg)
    reply = await agent.run(None, "u1", [], "执行安全操作")
    assert reply == "完成"
    assert executed == ["yes"]


async def _create_todo(client: AsyncClient, headers: dict) -> str:
    resp = await client.post(
        "/api/v1/todos", json={"title": "待删除任务"}, headers=headers
    )
    return resp.json()["data"]["id"]


def _delete_llm(todo_id: str):
    class DeleteLLM:
        async def chat(self, messages, tools=None, temperature=0.7, response_format=None):
            return ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="todo_delete",
                        arguments=json.dumps({"todo_id": todo_id}),
                    )
                ],
            )

    return DeleteLLM()


async def _chat_with_delete(monkeypatch, authed_headers, todo_id):
    from app.api.routes import chat as chat_module

    monkeypatch.setattr(chat_module, "get_llm", lambda: _delete_llm(todo_id))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat", json={"message": "删除这个待办"}, headers=authed_headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        sid = body["session_id"]
        assert "确认" in body["reply"]
        return client, sid


async def test_chat_pending_then_confirm_executes(monkeypatch, authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        todo_id = await _create_todo(client, authed_headers)

        from app.api.routes import chat as chat_module

        monkeypatch.setattr(chat_module, "get_llm", lambda: _delete_llm(todo_id))
        resp = await client.post(
            "/api/v1/chat", json={"message": "删除这个待办"}, headers=authed_headers
        )
        body = resp.json()["data"]
        sid = body["session_id"]
        assert "确认" in body["reply"]

        # 待办仍在（未执行）
        todos = (await client.get("/api/v1/todos", headers=authed_headers)).json()["data"]["items"]
        assert any(t["id"] == todo_id for t in todos)

        # 上一条助手消息带 pending_confirmation
        messages = (
            await client.get(f"/api/v1/sessions/{sid}/messages", headers=authed_headers)
        ).json()["data"]
        pending = messages[-1]["extra"].get("pending_confirmation")
        assert pending and pending[0]["name"] == "todo_delete"

        # 确认执行
        confirm = await client.post(
            "/api/v1/chat/confirm",
            json={"session_id": sid, "approve": True},
            headers=authed_headers,
        )
        assert confirm.status_code == 200, confirm.text
        assert "已执行" in confirm.json()["data"]["reply"]

        todos = (await client.get("/api/v1/todos", headers=authed_headers)).json()["data"]["items"]
        assert not any(t["id"] == todo_id for t in todos)


async def test_chat_pending_then_cancel_keeps(monkeypatch, authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        todo_id = await _create_todo(client, authed_headers)

        from app.api.routes import chat as chat_module

        monkeypatch.setattr(chat_module, "get_llm", lambda: _delete_llm(todo_id))
        resp = await client.post(
            "/api/v1/chat", json={"message": "删除这个待办"}, headers=authed_headers
        )
        sid = resp.json()["data"]["session_id"]

        cancel = await client.post(
            "/api/v1/chat/confirm",
            json={"session_id": sid, "approve": False},
            headers=authed_headers,
        )
        assert cancel.status_code == 200
        assert "已取消" in cancel.json()["data"]["reply"]

        todos = (await client.get("/api/v1/todos", headers=authed_headers)).json()["data"]["items"]
        assert any(t["id"] == todo_id for t in todos)


async def test_confirm_without_pending_returns_400(authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/sessions", json={}, headers=authed_headers)
        sid = created.json()["data"]["id"]
        resp = await client.post(
            "/api/v1/chat/confirm",
            json={"session_id": sid, "approve": True},
            headers=authed_headers,
        )
    assert resp.status_code == 400


async def test_chat_stream_emits_pending_event(monkeypatch, authed_headers):
    """流式对话遇到挂起操作时，SSE 应发出 pending 事件。"""
    from app.api.routes import chat as chat_module

    class FakeAgent:
        pending_confirmation: ClassVar[list[dict]] = [
            {"name": "todo_delete", "arguments": '{"todo_id":"x"}', "tool_call_id": "1"}
        ]
        last_tool_calls: ClassVar[list[dict]] = []

        async def run_stream(self, **kwargs):
            yield "以下操作需要你确认"

        async def close(self):
            pass

    monkeypatch.setattr(chat_module, "_build_agent", lambda: FakeAgent())
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "删除待办"},
            headers=authed_headers,
        ) as resp,
    ):
        assert resp.status_code == 200
        text = "".join([chunk async for chunk in resp.aiter_text()])
    assert "event: pending" in text
    assert "todo_delete" in text
    assert "event: done" in text
