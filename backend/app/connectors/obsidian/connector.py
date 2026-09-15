"""Obsidian 连接器实现：把本地 vault（服务器路径 / zip）同步为知识索引。"""

from app.connectors.base import SourceConnector, register_connector
from app.connectors.obsidian import service


class ObsidianConnector(SourceConnector):
    name = "obsidian"

    async def create_space(
        self,
        db,
        user_id,
        name: str,
        *,
        server_path: str | None = None,
        source_type: str | None = None,
    ):
        resolved = source_type or ("local" if server_path else "upload")
        return await service.create_space(
            db, user_id, name, source_type=resolved, server_path=server_path
        )

    async def import_archive(self, db, user_id, space, data: bytes) -> int:
        return await service.import_zip(db, user_id, space, data)

    async def import_files(self, db, user_id, space, items: list) -> int:
        return await service.import_files(db, user_id, space, items)

    async def sync(self, db, user_id, space) -> dict:
        return await service.sync_space(db, user_id, space)


connector = register_connector(ObsidianConnector())
