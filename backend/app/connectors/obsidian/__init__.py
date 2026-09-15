"""Obsidian 连接器。

保持 `__init__` 轻量：不在此导入 service/parser（避免与 `app.rag.parsers`
注册链形成循环导入）。使用方直接从子模块导入：
`app.connectors.obsidian.service` / `.parser` / `.links`。
"""
