"""pytest 全局配置：测试使用独立 SQLite 库，不污染开发数据库。

环境变量必须在导入 app 之前设置（settings 为模块级缓存）。
"""

import os
import uuid as _uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_copilot.db"
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

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models
from app.core.crypto import encrypt_secret
from app.core.db import Base, async_session_factory, engine
from app.main import app
from app.models import LLMSetting, User

_TEST_DB = "test_copilot.db"


@pytest.fixture
async def authed_headers() -> dict:
    """建表 + 注册测试用户，返回 Authorization 头与用户 id。

    默认给该用户播种一份**假的个人模型配置**：聊天链路要求用户自配 Key
    （env Key 仅超级管理员可用），所以绝大多数用例需要一个“已配置”的用户。
    需要“新账号未配置”语义时改用 `unconfigured_headers`。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
    """每个测试开始前清理残留文件，结束后释放引擎并删除测试库。"""
    # 测试前：清除上次运行可能残留的测试库
    if os.path.exists(_TEST_DB):
        try:
            os.remove(_TEST_DB)
        except PermissionError:
            pass
    yield
    from app.core.db import engine as app_engine

    await app_engine.dispose()
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)


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
    """提供独立的测试数据库会话（自动建表 + 用后清理）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///./{_TEST_DB}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()
