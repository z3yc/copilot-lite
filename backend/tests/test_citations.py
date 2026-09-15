"""结构化引用测试：kb_search 写入上下文 + chat 落库 Message.extra.citations。"""

from typing import ClassVar

from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.tools import registry
from app.tools.base import ToolContext


async def test_kb_search_writes_citations(monkeypatch):
    from app.tools import kb_tool as kb_module

    async def fake_hybrid_search(**_kwargs):
        from app.rag.retriever import RetrievedChunk

        return [
            RetrievedChunk(
                chunk_id="c1",
                content="内容A",
                meta={"document_title": "文档X", "headings": ["第一章"]},
                score=0.5,
                document_id="d1",
            )
        ]

    monkeypatch.setattr(settings, "RAG_QUERY_REWRITE_ENABLED", False)
    monkeypatch.setattr(settings, "WIKI_LINK_EXPANSION_ENABLED", False)
    monkeypatch.setattr(kb_module, "hybrid_search", fake_hybrid_search)

    ctx = ToolContext(session=None, user_id="u1")
    await registry.execute("kb_search", '{"query": "问题"}', ctx)

    assert ctx.citations
    cite = ctx.citations[0]
    assert cite["index"] == 1
    assert cite["chunk_id"] == "c1"
    assert "文档X" in cite["source"]


async def test_chat_persists_citations(monkeypatch, authed_headers):
    from app.api.routes import chat as chat_module

    class FakeAgent:
        last_tool_calls: ClassVar[list] = []
        pending_confirmation: ClassVar[list] = []
        last_citations: ClassVar[list] = [
            {"index": 1, "chunk_id": "c1", "source": "文档X > 第一章", "snippet": "内容A"}
        ]

        async def run(self, **kwargs):
            return "根据资料，答案如下 [1]"

        async def close(self):
            pass

    monkeypatch.setattr(chat_module, "_build_agent", lambda: FakeAgent())

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
    last = messages[-1]
    assert last["extra"]["citations"][0]["source"] == "文档X > 第一章"
