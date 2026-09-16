"""知识来源连接器抽象（企业落地关键 seam）。

定位：**Obsidian 只是"一种连接器"**。未来接入 S3 / SharePoint / Confluence / Git
只需实现 `SourceConnector` 并注册，检索、权限（ACL）、Agent 工具链路**不感知具体来源**。

约定：
- 连接器负责把外部知识源同步为系统内的 `documents` / `chunks`（派生索引）；
- 外部源始终是"单一事实源"，本系统索引可随时重建（read model）。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


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
    async def import_files(self, db, user_id, space, items: list) -> int:
        """导入单/多文件（可带相对路径），返回写入文件数。"""

    @abstractmethod
    async def sync(self, db, user_id, space) -> dict:
        """扫描连接器数据源并增量同步索引，返回统计。"""

    async def describe_sources(self, db, user_id, document_ids: list[str]) -> dict[str, dict]:
        """按 `document_id` 返回引用所需的来源身份（**可选能力**）。

        默认返回空：不提供来源身份的连接器无需实现。
        检索/工具层据此展示来源标签与跳转目标，**不感知具体来源**（AGENTS §12）。
        返回形如 `{document_id: {"kind": "wiki", "page_id": ..., ...}}`。
        """
        return {}


_REGISTRY: dict[str, SourceConnector] = {}


def register_connector(connector: SourceConnector) -> SourceConnector:
    _REGISTRY[connector.name] = connector
    return connector


def get_connector(name: str) -> SourceConnector | None:
    return _REGISTRY.get(name)


def available_connectors() -> list[str]:
    return list(_REGISTRY)


async def collect_source_meta(db, user_id, document_ids: list[str]) -> dict[str, dict]:
    """汇总各连接器提供的来源身份（`document_id` → 身份 dict）。

    增强能力：单个连接器失败只记警告并跳过——来源标注不能拖垮检索主链路
    （AGENTS §10）。无 db 或无事发文档时零成本返回（不触发查询）。
    """
    if db is None or not document_ids:
        return {}
    merged: dict[str, dict] = {}
    for connector in _REGISTRY.values():
        try:
            merged.update(await connector.describe_sources(db, user_id, document_ids) or {})
        except Exception:
            logger.warning("连接器 %s 来源身份解析失败", connector.name, exc_info=True)
    return merged
