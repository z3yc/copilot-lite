"""健康检查分层测试：存活/就绪探针 + 依赖探活降级。"""

from httpx import ASGITransport, AsyncClient

from app.api.routes import health as health_module
from app.main import app


async def test_live_probe_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_probe_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] is True
    assert body["checks"]["vector_store"] is True


async def test_ready_degraded_when_vector_store_down(monkeypatch):
    monkeypatch.setattr(health_module, "_check_vector_store", lambda: False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["vector_store"] is False


async def test_check_database_false_on_error(monkeypatch):
    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(health_module, "async_session_factory", lambda: _Boom())
    assert await health_module._check_database() is False


def test_check_vector_store_false_on_error(monkeypatch):
    def _boom():
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(health_module.vector_store_module, "get_qdrant_client", _boom)
    assert health_module._check_vector_store() is False
