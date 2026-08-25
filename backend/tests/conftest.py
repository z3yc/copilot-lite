"""pytest 全局配置：测试使用独立 SQLite 库，不污染开发数据库。

环境变量必须在导入 app 之前设置（settings 为模块级缓存）。
"""

import os
import uuid as _uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_copilot.db"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models
from app.core.db import Base, engine
from app.main import app

_TEST_DB = "test_copilot.db"


@pytest.fixture
async def authed_headers() -> dict:
    """建表 + 注册测试用户，返回 Authorization 头与用户 id。"""
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
        data = resp.json()
    return {"Authorization": f"Bearer {data['token']}", "uid": data["user"]["id"]}


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
