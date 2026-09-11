"""知识来源连接器抽象（企业落地关键 seam）。

定位：**Obsidian 只是"一种连接器"**。未来接入 S3 / SharePoint / Confluence / Git
只需实现 `SourceConnector` 并注册，检索、权限（ACL）、Agent 工具链路**不感知具体来源**。

约定：
- 连接器负责把外部知识源同步为系统内的 `documents` / `chunks`（派生索引）；
- 外部源始终是"单一事实源"，本系统索引可随时重建（read model）。
"""

from abc import ABC, abstractmethod
from typing import Any


class ConnectorError(Exception):
    """连接器业务错误（路径非法/来源不可用等）。"""


class SourceConnector(ABC):
    """知识来源连接器接口。"""

    # 连接器类型标识（如 obsidian）
    name: str = ""

    @abstractmethod
    async def create_space(
        self,
        db,
        user_id,
        name: str,
        *,
        server_path: str | None = None,
        source_type: str | None = None,
    ) -> Any:
        """创建一个知识空间（一个 vault / 一个数据源绑定）。"""

    @abstractmethod
    async def import_archive(self, db, user_id, space, data: bytes) -> int:
        """导入归档数据（如 zip），返回写入文件数。"""

    @abstractmethod
    async def sync(self, db, user_id, space) -> dict:
        """扫描连接器数据源并增量同步索引，返回统计。"""


_REGISTRY: dict[str, SourceConnector] = {}


def register_connector(connector: SourceConnector) -> SourceConnector:
    _REGISTRY[connector.name] = connector
    return connector


def get_connector(name: str) -> SourceConnector | None:
    return _REGISTRY.get(name)


def available_connectors() -> list[str]:
    return list(_REGISTRY)
