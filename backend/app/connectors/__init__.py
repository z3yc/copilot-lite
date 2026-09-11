"""连接器包。

保持 `__init__` 轻量：不在此导入具体连接器（避免与 `app.rag.parsers`
的注册链形成循环导入）。使用方直接从子模块导入，例如
`app.connectors.obsidian.connector`。
"""

from app.connectors.base import (
    ConnectorError,
    SourceConnector,
    available_connectors,
    get_connector,
    register_connector,
)

__all__ = [
    "ConnectorError",
    "SourceConnector",
    "available_connectors",
    "get_connector",
    "register_connector",
]
