"""可插拔工具注册表：Agent 调用工具的抽象层。

设计要点（面试可深挖）：
- 新增一个工具 = 写一个 async 函数 + 一行 @tool 装饰器，零其他改动；
- 工具参数 JSON Schema 从函数签名自动生成（类型映射 + 必填推断）；
- ToolContext 注入运行上下文（数据库会话、当前用户），工具函数无感使用；
- execute() 统一完成 JSON 参数解析（含类型容错）→ 调用 → 结果序列化，异常兜底。

多智能体扩展点（Post-MVP，见 README 路线图"后续规划"）：
- Agent-as-Tool：子 Agent 可注册为工具（name=agent 名，func=agent.run 的包装），
  由调度 Agent 通过既有 execute() 协议调用，无需新增机制；
- 工具即能力边界：领域能力（知识库检索/代码执行等）均以工具注册，
  后续 RouterAgent 只做意图路由，能力仍由注册表统一管理。
"""

import inspect
import json
import logging
import types
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Python 类型 → JSON Schema 类型
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

# 工具函数首个参数固定为 ctx，不参与 schema 生成
_CTX_PARAM = "ctx"


def _json_type(annotation: Any) -> str:
    """注解 → JSON Schema 类型（支持 Optional[str]/int|None 等联合类型剥壳）。"""
    if annotation is inspect.Parameter.empty:
        return "string"
    origin = get_origin(annotation)
    if origin is not None and origin in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if not args:
            return "string"
        annotation = args[0]  # 取唯一非 None 类型后继续解析（list[str] | None → array）
        origin = get_origin(annotation)
    if origin is not None:
        return _TYPE_MAP.get(origin, "string")
    return _TYPE_MAP.get(annotation, "string")


@dataclass
class ToolContext:
    """工具执行上下文：由编排器注入。"""

    session: AsyncSession
    user_id: Any | None = None


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., Awaitable[Any]]
    parameters: dict

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI Function Calling 的 tools 定义。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _build_parameters(func: Callable) -> dict:
    """从函数签名生成 JSON Schema（排除 ctx 参数）。"""
    sig = inspect.signature(func)
    properties: dict[str, dict] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == _CTX_PARAM:
            continue
        ptype = _json_type(param.annotation)
        prop: dict[str, Any] = {"type": ptype}
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)
        properties[name] = prop
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _coerce_value(value: Any, js_type: str) -> Any:
    """按 JSON Schema 类型强制转换单个参数值。

    背景：LLM 工具调用经常把整数/布尔/数组写成字符串（如 priority: "5"），
    直接传给 Python 函数会因类型不匹配抛错（例如 min(5, "5")）。
    这里按 schema 声明的类型做宽容转换，转换失败抛 TypeError 由 execute 兜底。
    """
    if value is None:
        return None
    if js_type == "integer":
        if isinstance(value, bool):  # bool 是 int 子类，先排除
            raise TypeError(f"期望整数，收到布尔值 {value!r}")
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"期望整数，收到 {value!r}") from exc
    if js_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"期望数字，收到 {value!r}") from exc
    if js_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("true", "1", "yes", "on"):
                return True
            if low in ("false", "0", "no", "off"):
                return False
        raise TypeError(f"期望布尔值，收到 {value!r}")
    if js_type in ("array", "object") and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise TypeError(f"期望 {js_type}，收到字符串 {value!r}") from exc
    return value


class ToolRegistry:
    """工具注册表：注册 / 查询 / 执行。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, func: Callable) -> Callable:
        """装饰器：注册一个工具函数。

        工具函数约定：
        - 第一个参数为 ctx: ToolContext（由执行器注入，不进入 schema）；
        - 其余参数为工具入参，从函数签名自动生成 JSON Schema；
        - 函数 docstring 的第一行作为工具描述。
        """
        name = func.__name__
        if name in self._tools:
            raise ValueError(f"工具重复注册: {name}")
        description = (func.__doc__ or "").strip().splitlines()[0]
        tool = Tool(
            name=name,
            description=description,
            func=func,
            parameters=_build_parameters(func),
        )
        self._tools[name] = tool
        logger.debug("已注册工具: %s", name)
        return func

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        """返回全部工具的 OpenAI tools 定义（按注册顺序）。"""
        return [t.to_openai_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, arguments: str, ctx: ToolContext) -> str:
        """执行工具：解析 JSON 参数（含类型容错）→ 调用 → 序列化结果。

        任何异常都被捕获并转为字符串返回，避免中断 ReAct 循环。
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：工具 {name} 不存在，可用工具: {', '.join(self.names())}"

        try:
            kwargs = json.loads(arguments) if arguments else {}
            # 按 schema 声明的类型强制转换（容忍 LLM 传 "5" 而非 5 等类型漂移）
            kwargs = self._coerce_args(tool.parameters, kwargs)
            result = await tool.func(ctx, **kwargs)
            # 字符串结果原样返回（避免二次序列化）；其他类型统一 JSON 序列化
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            return f"错误：工具 {name} 参数不合法 - {exc}"
        except Exception as exc:
            logger.exception("工具 %s 执行异常", name)
            return f"错误：工具 {name} 执行失败 - {exc}"

    @staticmethod
    def _coerce_args(parameters: dict, kwargs: dict) -> dict:
        """按工具 JSON Schema 对每个参数做类型强制转换。"""
        props = parameters.get("properties", {})
        out = dict(kwargs)
        for key, value in kwargs.items():
            prop = props.get(key)
            if prop and value is not None:
                out[key] = _coerce_value(value, prop.get("type", "string"))
        return out


# 全局单例：各工具模块通过 @tool 注册
registry = ToolRegistry()
