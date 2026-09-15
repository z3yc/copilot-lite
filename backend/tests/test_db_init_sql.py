"""初始化 SQL 生成器的回归测试（PostgreSQL 单方言）。

重点防两类已发生的坑：
1. `CreateTable/CreateIndex.compile()` 不带分号 → 生成的文件语句粘连（psql 报语法错误）；
2. 产物与 ORM 元数据 / 迁移 head 漂移。
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import db_init_sql

from app.core.db import Base

_ARTIFACT = pathlib.Path(__file__).resolve().parents[2] / "deploy" / "sql" / "init_postgres.sql"


class TestRender:
    """产物结构（不连库、不下载模型）。"""

    def test_covers_all_tables(self) -> None:
        sql = db_init_sql._render()
        # 每张表一条 CREATE TABLE IF NOT EXISTS，外加 alembic_version
        assert sql.count("CREATE TABLE IF NOT EXISTS") == len(Base.metadata.tables) + 1
        assert sql.count("CREATE INDEX IF NOT EXISTS") > 0
        for table in Base.metadata.tables:
            assert f"CREATE TABLE IF NOT EXISTS {table} " in sql

    def test_statements_are_semicolon_separated(self) -> None:
        """回归：缺分号会让整个文件变成一条坏语句（实测曾导致 psql 语法错误）。"""
        sql = db_init_sql._render()
        assert ")\nCREATE" not in sql
        assert not re.search(r"CREATE[^\n]*CREATE", sql)

    def test_keeps_partial_unique_index(self) -> None:
        """软删除的部分唯一索引不能丢（user.py 的 postgresql_where）。"""
        assert "deleted_at IS NULL" in db_init_sql._render()

    def test_writes_current_alembic_head(self) -> None:
        assert f"'{db_init_sql._head_revision()}'" in db_init_sql._render()

    def test_no_other_dialect_remnants(self) -> None:
        """已统一 PostgreSQL：产物不应再出现其它方言痕迹。"""
        sql = db_init_sql._render().lower()
        assert "sqlite" not in sql
        assert "autoincrement" not in sql  # SQLite 风格自增（PG 用 IDENTITY/SERIAL）


class TestArtifact:
    """仓库中提交的产物必须与当前模型一致（等价于 CI 的 --check）。"""

    def test_artifact_in_sync(self) -> None:
        assert _ARTIFACT.exists(), f"缺少产物：{_ARTIFACT}"
        assert _ARTIFACT.read_text(encoding="utf-8") == db_init_sql._render()
