"""长期记忆测试：提取（mock LLM）、存储、API 管理。"""

import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import DEFAULT_USER_ID
from app.main import app
from app.memory.service import MemoryService
from app.models import MemoryFact


class FakeEmbeddings512:
    """512 维确定性伪嵌入（匹配记忆向量维度，不下载模型）。"""

    dim = 512

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = hashlib.md5(t.encode()).hexdigest()
            # 循环取 hash 字节扩展到 512 维
            vec = [float(int(h[(i * 2) % 32 : (i * 2) % 32 + 2], 16)) / 255.0 for i in range(512)]
            out.append(vec)
        return out


class FakeExtractLLM:
    """返回预设事实 JSON 的假模型。"""

    def __init__(self, content: str) -> None:
        self.content = content

    async def chat(self, messages, tools=None, temperature=0.7):
        from app.core.llm import ChatResult

        return ChatResult(content=self.content)

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_extract_from_session(monkeypatch, db_session) -> None:
    """会话结束提取：LLM 输出事实 → 入库。"""
    import app.memory.service as mem_module

    monkeypatch.setattr(
        mem_module,
        "get_llm",
        lambda: FakeExtractLLM(
            '[{"fact": "我在准备后端开发面试", "category": "background", "confidence": 0.9}]'
        ),
    )
    # 跳过向量去重（避免维度/存储依赖）
    async def _no_dup(self, fact, user_id):
        return False

    monkeypatch.setattr(MemoryService, "_is_duplicate", _no_dup)

    svc = MemoryService(embeddings=FakeEmbeddings512())
    sid = uuid.uuid4()
    added = await svc.extract_from_session(
        db_session,
        DEFAULT_USER_ID,
        sid,
        [
            {"role": "user", "content": "我在准备后端面试"},
            {"role": "assistant", "content": "好的，祝你顺利！"},
        ],
    )
    assert added == 1

    from sqlalchemy import select

    rows = (await db_session.scalars(select(MemoryFact))).all()
    assert len(rows) == 1
    assert rows[0].fact == "我在准备后端开发面试"
    assert rows[0].category == "background"


@pytest.mark.asyncio
async def test_extract_empty_and_fallback(monkeypatch, db_session) -> None:
    """无事实返回 0；LLM 返回非法 JSON 不抛错。"""
    import app.memory.service as mem_module

    monkeypatch.setattr(mem_module, "get_llm", lambda: FakeExtractLLM("[]"))
    svc = MemoryService(embeddings=FakeEmbeddings512())

    added = await svc.extract_from_session(
        db_session, DEFAULT_USER_ID, uuid.uuid4(), [{"role": "user", "content": "你好"}]
    )
    assert added == 0

    # 非法 JSON
    monkeypatch.setattr(mem_module, "get_llm", lambda: FakeExtractLLM("不是JSON"))
    added = await svc.extract_from_session(
        db_session, DEFAULT_USER_ID, uuid.uuid4(), [{"role": "user", "content": "你好"}]
    )
    assert added == 0


@pytest.mark.asyncio
async def test_recall(db_session) -> None:
    """记忆召回：入库后按问题检索命中（相同文本保证向量一致）。"""
    svc = MemoryService(embeddings=FakeEmbeddings512())
    await svc._store(
        db_session,
        DEFAULT_USER_ID,
        uuid.uuid4(),
        "用户喜欢简洁回答",
        {"category": "preference", "confidence": 0.9},
    )

    results = await svc.recall(db_session, DEFAULT_USER_ID, "用户喜欢简洁回答")
    assert results and "简洁回答" in results[0]


@pytest.mark.asyncio
async def test_recall_user_isolation(db_session) -> None:
    """记忆召回按用户隔离：只召回自己的记忆（回归：跨用户记忆泄露）。"""
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    svc = MemoryService(embeddings=FakeEmbeddings512())
    await svc._store(
        db_session, user_a, uuid.uuid4(), "用户喜欢简洁回答", {"category": "preference"}
    )
    await svc._store(
        db_session, user_b, uuid.uuid4(), "用户喜欢详细回答", {"category": "preference"}
    )

    results_a = await svc.recall(db_session, user_a, "用户喜欢简洁回答")
    assert results_a, "应召回用户 A 自己的记忆"
    assert any("简洁" in r for r in results_a)
    assert all("详细" not in r for r in results_a), "绝不能召回用户 B 的记忆"


@pytest.mark.asyncio
async def test_delete_removes(db_session) -> None:
    """删除记忆：表记录移除且返回 True；不存在返回 False。"""
    from sqlalchemy import select

    svc = MemoryService(embeddings=FakeEmbeddings512())
    await svc._store(
        db_session, DEFAULT_USER_ID, uuid.uuid4(), "待删除的记忆", {"category": "fact"}
    )
    row = (await db_session.scalars(select(MemoryFact))).all()[0]

    ok = await svc.delete(db_session, DEFAULT_USER_ID, row.id)
    assert ok is True
    assert (await db_session.scalars(select(MemoryFact))).all() == []

    not_ok = await svc.delete(db_session, DEFAULT_USER_ID, uuid.uuid4())
    assert not_ok is False


@pytest.mark.asyncio
async def test_update_memory(db_session) -> None:
    """编辑记忆：修正事实与分类。"""
    from sqlalchemy import select

    svc = MemoryService(embeddings=FakeEmbeddings512())
    await svc._store(
        db_session,
        DEFAULT_USER_ID,
        uuid.uuid4(),
        "我在准备后端面试",
        {"category": "background"},
    )
    row = (await db_session.scalars(select(MemoryFact))).all()[0]

    ok = await svc.update(db_session, DEFAULT_USER_ID, row.id, "我在准备前端面试", "fact")
    assert ok is True
    await db_session.refresh(row)
    assert row.fact == "我在准备前端面试"
    assert row.category == "fact"

    # 越权/不存在返回 False
    not_ok = await svc.update(db_session, DEFAULT_USER_ID, uuid.uuid4(), "x", "fact")
    assert not_ok is False


@pytest.mark.asyncio
async def test_memories_api(authed_headers: dict) -> None:
    """记忆 API：列表与删除。"""

    from app.core.db import async_session_factory

    async with async_session_factory() as db:
        db.add(
            MemoryFact(
                user_id=uuid.UUID(authed_headers["uid"]),
                fact="测试记忆条目",
                category="fact",
                confidence=0.8,
            )
        )
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 列表
        r = await client.get("/api/v1/memories", headers=authed_headers)
        assert r.status_code == 200
        data = r.json()
        assert any(m["fact"] == "测试记忆条目" for m in data)
        mid = next(m["id"] for m in data if m["fact"] == "测试记忆条目")

        # 删除
        r = await client.delete(f"/api/v1/memories/{mid}", headers=authed_headers)
        assert r.status_code == 200
        r = await client.get("/api/v1/memories", headers=authed_headers)
        assert all(m["id"] != mid for m in r.json())
