"""初始化 SQL 生成器的回归测试。

重点防两类已发生的坑：
1. `CreateTable/CreateIndex.compile()` 不带分号 → 生成的文件语句粘连（psql 报语法错误）；
2. 产物与 ORM 元数据/迁移 head 漂移。
"""

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import db_init_sql

from app.core.db import Base

DIALECTS = ("postgres", "sqlite")


class TestRender:
    """产物结构（不连库、不下载模型）。"""

    @pytest.mark.parametrize("dialect", DIALECTS)
    def test_covers_all_tables_and_is_idempotent(self, dialect: str) -> None:
        sql = db_init_sql._render(dialect)
        # 每张表一条 CREATE TABLE IF NOT EXISTS，外加 alembic_version
        assert sql.count("CREATE TABLE IF NOT EXISTS") == len(Base.metadata.tables) + 1
        assert sql.count("CREATE INDEX IF NOT EXISTS") > 0
        for table in Base.metadata.tables:
            assert f"CREATE TABLE IF NOT EXISTS {table} " in sql

    @pytest.mark.parametrize("dialect", DIALECTS)
    def test_statements_are_semicolon_separated(self, dialect: str) -> None:
        """回归：缺分号会让整个文件变成一条坏语句（实测曾导致 psql 语法错误）。"""
        sql = db_init_sql._render(dialect)
        assert ")\nCREATE" not in sql
        assert not re.search(r"CREATE[^\n]*CREATE", sql)

    def test_postgres_keeps_partial_unique_index(self) -> None:
        """软删除的部分唯一索引不能丢（user.py 的 postgresql_where）。"""
        assert "deleted_at IS NULL" in db_init_sql._render("postgres")

    @pytest.mark.parametrize("dialect", DIALECTS)
    def test_writes_current_alembic_head(self, dialect: str) -> None:
        assert f"'{db_init_sql._head_revision()}'" in db_init_sql._render(dialect)


class TestSqliteImport:
    """真实导入一遍（内存库），验证 DDL 可执行且幂等。"""

    def test_import_twice(self) -> None:
        sql = db_init_sql._render("sqlite")
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(sql)
            con.executescript(sql)  # 幂等：第二次不应报错
            tables = {
                row[0] for row in con.execute("select name from sqlite_master where type='table'")
            }
            assert {"users", "documents", "chunks", "alembic_version"} <= tables
            assert len(tables) == len(Base.metadata.tables) + 1
            version = con.execute("select version_num from alembic_version").fetchone()[0]
            assert version == db_init_sql._head_revision()
        finally:
            con.close()
