"""Obsidian 解析器注册入口。

实现在 `app.connectors.obsidian.parser`（与 Obsidian 连接器同包）；
此处仅做注册触发，保持解析器包 `app/rag/parsers/` 的约定（导入即注册）。
"""

from app.connectors.obsidian.parser import WikiParser

__all__ = ["WikiParser"]
