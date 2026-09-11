"""请求上下文测试：request_id 中间件 + 日志过滤器注入。"""

import logging

from httpx import ASGITransport, AsyncClient

from app.core.context import (
    get_request_id,
    get_user_id,
    request_id_var,
    user_id_var,
)
from app.core.logging import ContextFilter
from app.main import app


async def test_request_id_generated_and_returned():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id")


async def test_request_id_forwarded_when_provided():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/health", headers={"X-Request-ID": "trace-abc-123"}
        )
    assert resp.headers.get("x-request-id") == "trace-abc-123"


def test_context_filter_injects_ids():
    rid_token = request_id_var.set("rid-1")
    uid_token = user_id_var.set("user-9")
    record = logging.LogRecord("t", logging.WARNING, __file__, 1, "boom", (), None)
    try:
        assert ContextFilter().filter(record) is True
        assert record.request_id == "rid-1"
        assert record.user_id == "user-9"
    finally:
        request_id_var.reset(rid_token)
        user_id_var.reset(uid_token)


def test_context_defaults_when_not_in_request():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hi", (), None)
    ContextFilter().filter(record)
    assert record.request_id == "-"
    assert get_request_id() == "-"
    assert get_user_id() == "-"
