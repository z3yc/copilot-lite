"""文档内容去重 + 失败重试测试（Fake 嵌入 + 隔离数据目录，不触网）。"""

import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import documents as docs_module
from app.main import app
from app.rag.vector_store import VectorStore


class FakeEmbeddings:
    """确定性伪嵌入（8 维）。"""

    dim = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            digest = hashlib.md5(text.encode()).hexdigest()
            out.append(
                [float(int(digest[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)]
            )
        return out


@pytest.fixture
def fake_rag(monkeypatch, tmp_path):
    """替换嵌入与向量库（8 维），并把原件目录隔离到 tmp。"""
    store = VectorStore(dimension=8)
    monkeypatch.setattr(docs_module, "get_embedding_service", lambda: FakeEmbeddings())
    monkeypatch.setattr(docs_module, "get_vector_store", lambda: store)
    monkeypatch.setattr(docs_module, "_DATA_DIR", tmp_path / "data")
    return store


async def _upload(client: AsyncClient, headers: dict, name: str, content: bytes):
    return await client.post(
        "/api/v1/documents/upload",
        files={"file": (name, content, "text/markdown")},
        headers=headers,
    )


async def test_upload_same_content_deduplicated(authed_headers, fake_rag) -> None:
    content = b"# Title\n\nHello world, unique content."
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await _upload(client, authed_headers, "a.md", content)
        assert first.status_code == 200, first.text
        second = await _upload(client, authed_headers, "b.md", content)
        assert second.status_code == 200, second.text
        assert first.json()["data"]["id"] == second.json()["data"]["id"]

        listing = await client.get("/api/v1/documents", headers=authed_headers)
        assert len(listing.json()["data"]["items"]) == 1


async def test_retry_failed_document(authed_headers, fake_rag, monkeypatch) -> None:
    original_ingest = docs_module.ingest_document

    async def _boom(*args, **kwargs):
        raise RuntimeError("模拟嵌入失败")

    monkeypatch.setattr(docs_module, "ingest_document", _boom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await _upload(client, authed_headers, "r.md", b"# retry\n\nbody")
        assert resp.status_code == 422

        listing = await client.get("/api/v1/documents", headers=authed_headers)
        doc = listing.json()["data"]["items"][0]
        assert doc["status"] == "failed"

        # 恢复真实摄取后重试
        monkeypatch.setattr(docs_module, "ingest_document", original_ingest)
        retry = await client.post(
            f"/api/v1/documents/{doc['id']}/retry", headers=authed_headers
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["data"]["status"] == "ready"
        assert retry.json()["data"]["chunk_count"] >= 1


async def test_retry_other_users_document_returns_404(authed_headers, fake_rag) -> None:
    content = b"# secret\n\nprivate"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await _upload(client, authed_headers, "s.md", content)
        doc_id = resp.json()["data"]["id"]

        other = await client.post(
            "/api/v1/auth/register",
            json={"username": f"u{uuid.uuid4().hex[:8]}", "password": "secret123"},
        )
        other_headers = {"Authorization": f"Bearer {other.json()["data"]['token']}"}
        retry = await client.post(
            f"/api/v1/documents/{doc_id}/retry", headers=other_headers
        )
        assert retry.status_code == 404
