"""文档列表接口回归测试：分块数批量统计（防 N+1 查询回归）。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.core.db import async_session_factory, engine
from app.main import app
from app.models import Chunk, Document


async def test_document_list_counts_without_n_plus_one(authed_headers: dict) -> None:
    """多文档列表：分块数应一次聚合查询得出，而非每文档一次 count。"""
    uid = uuid.UUID(authed_headers["uid"])
    async with async_session_factory() as db:
        for i in range(5):
            doc = Document(
                user_id=uid, title=f"doc-{i}", source_type="md", status="ready"
            )
            db.add(doc)
            await db.flush()
            db.add(Chunk(document_id=doc.id, chunk_index=0, content=f"内容{i}", meta={}))
        await db.commit()

    statements: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _before)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/documents", headers=authed_headers)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before)

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 5
    assert all(d["chunk_count"] == 1 for d in data)

    # N+1 修复前会是 5 条分块 count；修复后只应有一条 GROUP BY 聚合
    chunk_queries = [s for s in statements if "FROM chunks" in s]
    assert len(chunk_queries) == 1, chunk_queries
