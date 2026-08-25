"""会话附件接口测试（需认证）：上传/列表/删除 + chat 上下文注入。"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_session_files_crud(authed_headers: dict) -> None:
    """会话附件：创建会话 → 上传 → 列表 → 删除。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 创建会话
        r = await client.post("/api/v1/sessions", json={"title": "附件会话"}, headers=authed_headers)
        assert r.status_code == 200
        sid = r.json()["id"]

        # 上传附件（Markdown）
        r = await client.post(
            f"/api/v1/sessions/{sid}/files",
            files={"file": ("笔记.md", "## 第一章\n\n这是附件内容。".encode(), "text/markdown")},
            headers=authed_headers,
        )
        assert r.status_code == 200
        fid = r.json()["id"]

        # 列表
        r = await client.get(f"/api/v1/sessions/{sid}/files", headers=authed_headers)
        assert r.status_code == 200
        assert any(x["id"] == fid for x in r.json())

        # 删除
        r = await client.delete(f"/api/v1/sessions/{sid}/files/{fid}", headers=authed_headers)
        assert r.status_code == 200
        r = await client.get(f"/api/v1/sessions/{sid}/files", headers=authed_headers)
        assert r.json() == []


@pytest.mark.asyncio
async def test_chat_injects_session_files(monkeypatch, authed_headers: dict) -> None:
    """chat 时将附件内容作为 system 上下文注入。"""
    from app.api.routes import chat as chat_module
    from app.core.db import async_session_factory
    from app.core.llm import ChatResult
    from app.models import ChatSession, SessionFile

    captured: list[dict] = []

    class CaptureLLM:
        async def chat(self, messages, tools=None, temperature=0.7):
            captured.append(messages)
            return ChatResult(content="回复")

        async def close(self):
            pass

    async with async_session_factory() as db:
        s = ChatSession(user_id=uuid.UUID(authed_headers["uid"]), title="t")
        db.add(s)
        await db.commit()
        await db.refresh(s)
        db.add(
            SessionFile(
                session_id=s.id, filename="笔记.md", content="## 第一章\n附件独特内容XYZ"
            )
        )
        await db.commit()
        sid = str(s.id)

    monkeypatch.setattr(chat_module, "get_llm", lambda: CaptureLLM())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/chat",
            json={"message": "附件讲了什么", "session_id": sid},
            headers=authed_headers,
        )
    assert r.status_code == 200

    # 验证注入：消息序列中存在含附件内容的 system 上下文
    assert captured
    system_msgs = [m for m in captured[0] if m["role"] == "system"]
    assert any("笔记.md" in m["content"] for m in system_msgs)
    assert any("附件独特内容XYZ" in m["content"] for m in system_msgs)
