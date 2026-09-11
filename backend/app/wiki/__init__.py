"""Wiki 本地知识库接入（Obsidian 导入 → 索引 → 双链图）。

注意：本包 `__init__` 保持轻量，不在此导入 service/parser，
避免与 `app.rag.parsers`（解析器注册表）形成循环导入。
请直接从子模块导入：`app.wiki.service` / `app.wiki.parser` / `app.wiki.links`。
"""
