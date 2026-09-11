"""统一响应结构（信封）测试：成功包装 / 错误包装 / 边界不包装。"""

import json

from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError, code_for_status, envelope
from app.main import app


async def test_success_response_enveloped(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/sessions", headers=authed_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert isinstance(body["data"], dict)
    assert isinstance(body["data"]["items"], list)


async def test_http_error_enveloped_with_business_code() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/sessions")  # 未认证
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 1001
    assert body["message"] == "未登录"


async def test_not_found_error_enveloped(authed_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/sessions/not-a-uuid/messages", headers=authed_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == 2001


async def test_openapi_and_root_not_wrapped() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        spec = await client.get("/openapi.json")
        root = await client.get("/")
    assert "openapi" in spec.json()  # 未被包成 {code,...}
    assert "docs" in root.json()


async def test_validation_error_enveloped() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", json={})  # 缺字段
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 1000
    assert body["message"] == "参数校验失败"


def test_code_for_status_mapping() -> None:
    assert code_for_status(400) == 1000
    assert code_for_status(401) == 1001
    assert code_for_status(404) == 2001
    assert code_for_status(429) == 1002
    assert code_for_status(502) == 3001
    assert code_for_status(503) == 3002
    assert code_for_status(500) == 3000
    assert code_for_status(418) == 1000


def test_envelope_shape() -> None:
    assert envelope({"a": 1}) == {"code": 0, "message": "ok", "data": {"a": 1}}
    assert envelope(None, code=2001, message="不存在")["code"] == 2001


async def test_app_error_handler_uses_business_code() -> None:
    handler = app.exception_handlers[AppError]
    response = await handler(None, AppError("会话不存在", code=2001, status_code=404))
    assert response.status_code == 404
    assert json.loads(response.body)["code"] == 2001


async def test_unexpected_exception_enveloped() -> None:
    handler = app.exception_handlers[Exception]
    response = await handler(None, RuntimeError("boom"))
    assert response.status_code == 500
    assert json.loads(response.body)["code"] == 3000
