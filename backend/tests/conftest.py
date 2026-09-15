"""pytest 全局配置：测试使用独立 PostgreSQL 库（与生产同构）。

环境变量必须在导入 app 之前设置（settings 为模块级缓存）。

- 测试库：`TEST_DATABASE_URL`（默认 `postgresql+asyncpg://postgres:root@localhost:5432/copilot_test`）；
- 库不存在时自动创建（连维护库 `postgres` 执行 CREATE DATABASE）；
- 每个用例前 TRUNCATE 全部表，用例间互不影响；
- 统一 PG 的原因：SQLite 与 PG 的时区/级联/部分索引语义不同，曾出现
  "SQLite 测试通过、生产 PG 报错"的方言差异问题（AGENTS：本地只用 PG）。
"""

import os
import uuid as _uuid

_TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:root@localhost:5432/copilot_test",
)
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
# 测试环境关闭后台记忆提取（避免后台任务占用测试库句柄）
os.environ["MEMORY_EXTRACT_ENABLED"] = "false"
# 测试环境关闭后台摘要压缩（同上）
os.environ["SUMMARY_COMPRESS_ENABLED"] = "false"
# 测试环境关闭评测后台作业（后台任务必须默认关闭，AGENTS §8）
os.environ["EVAL_JOB_ENABLED"] = "false"
# 测试环境关闭通用后台作业（同上；wiki import/sync 用例默认走内联，关闭后行为同旧版）
os.environ["JOBS_ENABLED"] = "false"
# 测试环境关闭嵌入模型预热（避免下载模型）
os.environ["EMBEDDING_PREWARM"] = "false"
# 测试环境注入假 LLM Key（chat.py 的 _validate_llm_config 会校验 key 非空；
# 测试全程用 FakeLLM mock，不会真实调用 DeepSeek——避免 CI 无 .env 时误报 503）
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-real")

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.engine import make_url

import app.models
from app.core.constants import DEFAULT_USER_ID, DEFAULT_USERNAME
from app.core.crypto import encrypt_secret
from app.core.db import Base, async_session_factory, engine
from app.core.security import hash_password
from app.main import app
from app.models import LLMSetting, User

_schema_ready = False


async def _ensure_database() -> None:
    """测试库不存在则创建（连维护库 postgres，PG 无 CREATE DATABASE IF NOT EXISTS）。"""
    url = make_url(_TEST_DATABASE_URL)
    db_name = url.database or "copilot_test"
    try:
        conn = await asyncpg.connect(
            user=url.username,
            password=url.password,
            host=url.host,
            port=url.port or 5432,
            database="postgres",
        )
    except OSError as exc:  # 服务没起/端口不通——给出可操作的提示
        raise RuntimeError(
            f"连接测试库失败（{url.render_as_string(hide_password=True)}）："
            "请先启动 PostgreSQL（本地默认 localhost:5432）"
        ) from exc
    try:
        exists = await conn.fetchval("select 1 from pg_database where datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _ensure_schema() -> None:
    """建表（幂等；整个测试会话只需一次）。"""
    global _schema_ready
    if _schema_ready:
        return
    await _ensure_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _schema_ready = True


async def _truncate_all() -> None:
    """清空所有表（CASCADE 兼容外键；RESTART IDENTITY 重置自增序列）。"""
    names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


async def _seed_default_user() -> None:
    """预置单用户模式的默认用户（`DEFAULT_USER_ID`）。

    大量单测直接用该固定 id 作为数据归属：SQLite 默认不强制外键所以过去能过，
    PostgreSQL 强制外键——测试库里必须先存在这条用户记录。
    """
    async with async_session_factory() as db:
        db.add(
            User(
                id=DEFAULT_USER_ID,
                username=DEFAULT_USERNAME,
                password_hash=hash_password("test-not-real"),
                role="user",
            )
        )
        await db.commit()


@pytest.fixture
async def make_user():
    """创建真实用户并返回其 id（需要多个用户做隔离验证时用）。

    PostgreSQL 强制外键（SQLite 默认不强制），凡是用"临时造 UUID"归属数据的
    测试都必须先建出真实用户；单用户场景直接用已预置的 `DEFAULT_USER_ID`。
    """

    async def _make(username: str | None = None) -> _uuid.UUID:
        async with async_session_factory() as db:
            user = User(
                id=_uuid.uuid4(),
                username=username or f"u{_uuid.uuid4().hex[:8]}",
                password_hash=hash_password("test-not-real"),
                role="user",
            )
            db.add(user)
            await db.commit()
            return user.id

    return _make


@pytest.fixture
async def authed_headers() -> dict:
    """建表 + 注册测试用户，返回 Authorization 头与用户 id。

    默认给该用户播种一份**假的个人模型配置**：聊天链路要求用户自配 Key
    （env Key 仅超级管理员可用），所以绝大多数用例需要一个“已配置”的用户。
    需要“新账号未配置”语义时改用 `unconfigured_headers`。
    """
    await _ensure_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": f"u{_uuid.uuid4().hex[:8]}",
                "password": "secret123",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
    async with async_session_factory() as db:
        db.add(
            LLMSetting(
                user_id=_uuid.UUID(data["user"]["id"]),
                base_url="https://api.example.com",
                model="test-model",
                api_key_encrypted=encrypt_secret("sk-test-user-key"),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {data['token']}", "uid": data["user"]["id"]}


@pytest.fixture
async def admin_headers(authed_headers: dict) -> dict:
    """把已登录用户提升为管理员（role=admin），复用同款授权头。

    角色在每次请求时从 DB 读取，故改角色无需重签 token。
    """
    import uuid as _u

    async with async_session_factory() as db:
        user = await db.get(User, _u.UUID(authed_headers["uid"]))
        user.role = "admin"
        await db.commit()
    return authed_headers


@pytest.fixture
async def unconfigured_headers(authed_headers: dict) -> dict:
    """已登录但未自配模型 Key 的用户（模拟新注册账号）。"""
    async with async_session_factory() as db:
        await db.execute(
            delete(LLMSetting).where(
                LLMSetting.user_id == _uuid.UUID(authed_headers["uid"])
            )
        )
        await db.commit()
    return authed_headers


@pytest.fixture(autouse=True)
async def _clean_test_db():
    """每个用例前清空全部表；结束后释放引擎（避免连接池跨事件循环复用）。"""
    await _ensure_schema()
    await _truncate_all()
    await _seed_default_user()
    yield
    from app.core.db import engine as app_engine

    await app_engine.dispose()


@pytest.fixture(autouse=True)
def _disable_memory_recall(monkeypatch):
    """测试中禁用真实记忆召回（避免加载嵌入模型）。

    仅替换 chat 模块的 service 入口，不动 MemoryService 类本身，
    以便 test_memory 直接测真实实现。
    """
    from app.api.routes import chat as chat_module

    class _NoMemService:
        async def recall(self, *a, **k):
            return []

        async def extract_from_session(self, *a, **k):
            return 0

    monkeypatch.setattr(chat_module, "get_memory_service", lambda: _NoMemService())


@pytest.fixture(autouse=True)
def _handwritten_engine_default(monkeypatch):
    """测试默认走手写引擎（避免 LangGraph 引擎创建真实 ChatOpenAI/网络请求）。

    与 LangGraph 相关的测试显式设置 AGENT_ENGINE=langgraph 或注入 Fake 模型。
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "AGENT_ENGINE", "handwritten")


@pytest.fixture(autouse=True)
def _disable_rerank(monkeypatch):
    """测试默认关闭 Rerank 精排（避免加载真实 bge-reranker 模型）。

    相关测试显式 monkeypatch 开启开关并注入 Fake 重排器。
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "RAG_RERANK_ENABLED", False)


@pytest.fixture(autouse=True)
def _disable_query_rewrite(monkeypatch):
    """测试默认关闭查询改写（避免 kb_search 触发真实 LLM 改写调用）。

    相关测试显式开启开关并注入 Fake 改写器。
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "RAG_QUERY_REWRITE_ENABLED", False)


@pytest.fixture(autouse=True)
def _isolated_qdrant(tmp_path, monkeypatch):
    """隔离测试用 Qdrant 目录（避免污染开发库 ./qdrant_data 与目录锁冲突）。

    共享单例 client（Qdrant 本地模式同一目录只允许一个客户端实例）。
    """
    from qdrant_client import QdrantClient

    client = QdrantClient(path=str(tmp_path / "qdrant_data"))
    monkeypatch.setattr("app.rag.vector_store.get_qdrant_client", lambda: client)


@pytest.fixture
async def db_session():
    """提供独立的测试数据库会话（表已就绪，用后清理）。"""
    await _ensure_schema()
    async with async_session_factory() as session:
        yield session
