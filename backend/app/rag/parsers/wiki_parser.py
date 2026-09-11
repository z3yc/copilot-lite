"""Wiki 解析器注册入口。

实现在 `app.wiki.parser`（与 Wiki 服务同包）；此处仅做注册触发，
保持解析器包 `app/rag/parsers/` 的约定（导入即注册）。
"""

from app.wiki.parser import WikiParser

__all__ = ["WikiParser"]
