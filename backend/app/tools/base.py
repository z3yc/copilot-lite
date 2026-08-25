"""可插拔工具注册表：Agent 调用工具的抽象层。

设计要点（面试可深挖）：
- 新增一个工具 = 写一个 async 函数 + 一行 @tool 装饰器，零其他改动；
- 工具参数 JSON Schema 从函数签名自动生成（类型映射 + 必填推断）；
- ToolContext 注入运行上下文（数据库会话、当前用户），工具函数无感使用；
- execute() 统一完成 JSON 参数解析 → 调用 → 结果序列化，异常兜底。

多智能体扩展点（Post-MVP，见 README 路线图"后续规划"）：
- Agent-as-Tool：子 Agent 可注册为工具（name=agent 名，func=agent.run 的包装），
  由调度 Agent 通过既有 execute() 协议调用，无需新增机制；
- 工具即能力边界：领域能力（知识库检索/代码执行等）均以工具注册，
  后续 RouterAgent 只做意图路由，能力仍由注册表统一管理。
"""

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

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
        if param.annotation is inspect.Parameter.empty:
            ptype = "string"
        else:
            ptype = _TYPE_MAP.get(param.annotation, "string")
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
        """执行工具：解析 JSON 参数 → 调用 → 序列化结果。

        任何异常都被捕获并转为字符串返回，避免中断 ReAct 循环。
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：工具 {name} 不存在，可用工具: {', '.join(self.names())}"

        try:
            kwargs = json.loads(arguments) if arguments else {}
            result = await tool.func(ctx, **kwargs)
            return json.dumps(result, ensure_ascii=False, default=str)
        except TypeError as exc:
            return f"错误：工具 {name} 参数不合法 - {exc}"
        except Exception as exc:
            logger.exception("工具 %s 执行异常", name)
            return f"错误：工具 {name} 执行失败 - {exc}"


# 全局单例：各工具模块通过 @tool 注册
registry = ToolRegistry()
