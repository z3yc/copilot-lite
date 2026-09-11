"""统一业务异常与错误码（对齐 AGENTS.md §14）。

错误码分层：
- 1xxx 通用（参数 / 鉴权 / 限流 / 体积）
- 2xxx 业务（资源不存在 / 冲突）
- 3xxx LLM / Agent（模型不可用 / 服务暂不可用）

统一响应结构：``{"code": <int>, "message": <str>, "data": <any>}``；
成功 ``code=0``，错误 ``code>0``。
"""

from typing import Any

# HTTP 状态码 → 业务错误码
_HTTP_CODE_MAP: dict[int, int] = {
    400: 1000,
    401: 1001,
    403: 1003,
    404: 2001,
    409: 2002,
    413: 1004,
    422: 1000,
    429: 1002,
    502: 3001,
    503: 3002,
}

ERROR_MESSAGES: dict[int, str] = {
    1000: "参数错误",
    1001: "未认证",
    1002: "请求过于频繁",
    1003: "无权限",
    1004: "请求体过大",
    2001: "资源不存在",
    2002: "资源冲突",
    3000: "服务内部错误",
    3001: "模型服务不可用",
    3002: "服务暂不可用",
}


def code_for_status(status_code: int) -> int:
    """HTTP 状态码映射为业务错误码。"""
    if status_code in _HTTP_CODE_MAP:
        return _HTTP_CODE_MAP[status_code]
    return 3000 if status_code >= 500 else 1000


def envelope(data: Any = None, *, code: int = 0, message: str = "ok") -> dict:
    """构造统一响应结构。"""
    return {"code": code, "message": message, "data": data}


class AppError(Exception):
    """业务异常：由全局处理器转换为统一错误响应。

    用法：``raise AppError("会话不存在", code=2001, status_code=404)``
    """

    def __init__(
        self,
        message: str,
        *,
        code: int = 1000,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
