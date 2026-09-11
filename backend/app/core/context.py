"""请求级上下文：request_id / user_id 通过 contextvars 全链路传递。

设计（对齐 AGENTS.md §15）：
- ASGI 中间件在请求入口生成 `X-Request-ID`（或透传客户端传入值）；
- contextvars 随异步调用链自动传播（同一请求任务内全程可见），
  无需层层透传参数；
- 日志过滤器从 contextvar 读取，WARN/ERROR 日志自动携带 request_id / user_id。

注意：使用纯 ASGI 中间件而非 BaseHTTPMiddleware——后者会把下游放进独立
anyio 任务，导致 dispatch 中设置的 contextvar 无法传播到路由处理函数。
"""

import uuid
from contextvars import ContextVar

# 空串表示"非请求上下文"（如后台任务），日志展示为 "-"
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")

# 客户端可传入该请求头以贯穿分布式链路
REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> str:
    """当前请求 id（非请求上下文返回 "-"）。"""
    return request_id_var.get() or "-"


def get_user_id() -> str:
    """当前用户 id（未认证/非请求上下文返回 "-"）。"""
    return user_id_var.get() or "-"


def set_user_id(user_id: object | None) -> None:
    """登录成功后写入当前用户 id（供日志与审计）。"""
    user_id_var.set(str(user_id) if user_id else "")


def new_request_id() -> str:
    """生成短请求 id（32 位 uuid 取前 16 位，足够单机不碰撞）。"""
    return uuid.uuid4().hex[:16]


class RequestContextMiddleware:
    """纯 ASGI 中间件：注入 request_id 上下文 + 响应头回写。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(REQUEST_ID_HEADER.lower().encode())
        request_id = incoming.decode() if incoming else new_request_id()
        token = request_id_var.set(request_id)

        async def send_with_header(message):
            if message.get("type") == "http.response.start":
                raw_headers = list(message.get("headers") or [])
                raw_headers.append(
                    (REQUEST_ID_HEADER.lower().encode(), request_id.encode())
                )
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)
