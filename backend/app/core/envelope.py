"""统一响应结构包装（AGENTS.md §14）。

以纯 ASGI 中间件实现，仅在 **`/api/v1` 下、2xx、Content-Type 为 application/json**
的响应上包成 ``{code, message, data}``：

- SSE（text/event-stream）与文件下载（text/markdown 等）直接透传，不缓冲、不破坏流式；
- 错误响应（非 2xx）由全局异常处理器统一构造信封，中间件不干预；
- 仅作用于 /api/v1：不影响 /openapi.json、/docs 等框架路由。
"""

import json


class EnvelopeMiddleware:
    """把 /api/v1 的成功 JSON 响应包成统一结构。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or not scope.get("path", "").startswith("/api/v1"):
            await self.app(scope, receive, send)
            return

        state: dict = {"wrap": False, "status": 0, "headers": []}
        body = bytearray()

        async def send_wrapper(message) -> None:
            mtype = message["type"]
            if mtype == "http.response.start":
                headers = message.get("headers") or []
                content_type = ""
                for key, value in headers:
                    if key.lower() == b"content-type":
                        content_type = value.decode("latin-1").lower()
                state["wrap"] = (
                    200 <= message["status"] < 300 and "application/json" in content_type
                )
                state["status"] = message["status"]
                state["headers"] = headers
                if state["wrap"]:
                    return  # 延迟发送，等 body 收全后包壳
                await send(message)
            elif mtype == "http.response.body":
                if state["wrap"]:
                    body.extend(message.get("body", b""))
                    if not message.get("more_body", False):
                        await _send_wrapped(send, state, body)
                    return
                await send(message)
            else:
                await send(message)

        await self.app(scope, receive, send_wrapper)


async def _send_wrapped(send, state: dict, body: bytearray) -> None:
    try:
        payload = json.loads(bytes(body))
        content = json.dumps(
            {"code": 0, "message": "ok", "data": payload}, ensure_ascii=False
        ).encode("utf-8")
    except (ValueError, TypeError):  # 非 JSON，原样透传
        content = bytes(body)
    headers = [(k, v) for k, v in state["headers"] if k.lower() != b"content-length"]
    await send(
        {"type": "http.response.start", "status": state["status"], "headers": headers}
    )
    await send({"type": "http.response.body", "body": content, "more_body": False})
