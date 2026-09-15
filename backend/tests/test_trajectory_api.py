"""轨迹落库与 SSE 透传测试：Message.extra.trajectory + done 事件 payload。"""

import json
from typing import ClassVar

from httpx import ASGITransport, AsyncClient

from app.main import app

_FAKE_TRAJECTORY = {
    "engine": "langgraph",
    "total_ms": 120,
    "truncated": False,
    "steps": [
        {"type": "route", "route": "kb", "source": "llm", "ms": 40},
        {"type": "node", "node": "kb_agent"},
        {
            "type": "tool",
            "name": "kb_search",
            "arguments": "{}",
            "result": "片段",
            "status": "ok",
            "ms": 12,
        },
        {"type": "answer", "chars": 6},
    ],
}


class _FakeAgent:
    last_tool_calls: ClassVar[list] = []
    pending_confirmation: ClassVar[list] = []
    last_citations: ClassVar[list] = []
    last_trajectory: ClassVar[dict] = _FAKE_TRAJECTORY

    async def run(self, **kwargs):
        return "回答"

    async def run_stream(self, **kwargs):
        yield "回答"

    async def close(self):
        pass


class _FakeAgentNoTrajectory(_FakeAgent):
    last_trajectory: ClassVar[dict] = {}


async def test_chat_persists_trajectory(monkeypatch, authed_headers: dict) -> None:
    """给定一条消息能复原 路由/节点/工具/结果（§10.5 验收）。"""
    from app.api.routes import chat as chat_module

    monkeypatch.setattr(chat_module, "_build_agent", lambda: _FakeAgent())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat", json={"message": "问个问题"}, headers=authed_headers
        )
        assert resp.status_code == 200, resp.text
        sid = resp.json()["data"]["session_id"]
        messages = (
            await client.get(f"/api/v1/sessions/{sid}/messages", headers=authed_headers)
        ).json()["data"]

    traj = messages[-1]["extra"]["trajectory"]
    assert traj["engine"] == "langgraph"
    assert [s["type"] for s in traj["steps"]] == ["route", "node", "tool", "answer"]
    assert traj["steps"][0]["route"] == "kb"
    assert traj["steps"][2]["name"] == "kb_search"


async def test_chat_omits_trajectory_when_engine_returns_empty(
    monkeypatch, authed_headers: dict
) -> None:
    """引擎未产出轨迹（开关关闭）时不写空 key。"""
    from app.api.routes import chat as chat_module

    monkeypatch.setattr(chat_module, "_build_agent", lambda: _FakeAgentNoTrajectory())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat", json={"message": "你好"}, headers=authed_headers
        )
        sid = resp.json()["data"]["session_id"]
        messages = (
            await client.get(f"/api/v1/sessions/{sid}/messages", headers=authed_headers)
        ).json()["data"]
    assert "trajectory" not in (messages[-1]["extra"] or {})


async def test_chat_stream_done_event_carries_trajectory(
    monkeypatch, authed_headers: dict
) -> None:
    """SSE done 事件增量附带 trajectory（不新增事件类型、不改既有事件形状）。"""
    from app.api.routes import chat as chat_module

    monkeypatch.setattr(chat_module, "_build_agent", lambda: _FakeAgent())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST", "/api/v1/chat/stream", json={"message": "你好"}, headers=authed_headers
        ) as resp:
            events: list[str] = []
            done_payload: dict = {}
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events.append(line[7:])
                elif line.startswith("data: "):
                    body = json.loads(line[6:])
                    if "trajectory" in body:
                        done_payload = body

    assert events[0] == "session" and events[-1] == "done"
    assert done_payload["trajectory"]["steps"][2]["name"] == "kb_search"
