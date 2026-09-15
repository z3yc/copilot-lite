"""数据库初始化 SQL 生成器 —— 一键导入建库（表结构）。

用法（在 backend 目录）：
    uv run python scripts/db_init_sql.py                # 生成两方言到 deploy/sql/
    uv run python scripts/db_init_sql.py --dialect postgres
    uv run python scripts/db_init_sql.py --check        # 校验产物与模型一致（提交前/CI）

为什么不用 `alembic upgrade head --sql` 生成：
    历史迁移里有 6 个用 `op.get_bind()` + `sa.inspect()` 做方言条件 DDL，
    离线模式（MockConnection）不支持 introspection，会中途报错、产出残缺 SQL。
    因此这里直接以 **ORM 元数据**（`app.models` 的 `Base.metadata`）为单一源导出 DDL ——
    与 `RUN_MODE=local` 的 `create_all` 完全同源，不会与模型漂移。

产物（幂等，可重复导入；不含任何业务数据）：
    deploy/sql/init_postgres.sql   → psql -f / docker compose exec -T postgres psql
    deploy/sql/init_sqlite.sql     → sqlite3 导入（本地开发库）
末尾写入 `alembic_version`（stamp 当前 head），使之后 `alembic upgrade head` 不会重复建表。
"""

import argparse
import difflib
import sys
from pathlib import Path

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Dialect
from sqlalchemy.schema import CreateIndex, CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.config import Config
from alembic.script import ScriptDirectory

import app.models  # noqa: F401  确保所有模型注册到 Base.metadata
from app.core.db import Base

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _BACKEND_DIR.parent / "deploy" / "sql"
_DIALECTS = {"postgres": postgresql.dialect, "sqlite": sqlite.dialect}

_HEADER = """-- ⚠️ 本文件由脚本生成，请勿手工修改
-- 生成命令：cd backend && uv run python scripts/db_init_sql.py
-- 单一源：app/models 的 ORM 元数据（与 RUN_MODE=local 的 create_all 同源，勿手写 DDL）
-- 幂等：所有 DDL 带 IF NOT EXISTS，可重复导入
-- 内容：仅表结构 + alembic 版本标记；业务数据由应用启动时/接口负责
"""


def _head_revision() -> str:
    """当前迁移链 head（写入 alembic_version，避免导入后重复建表）。"""
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        raise SystemExit(f"迁移链存在多个 head（{heads}），请先收敛为单链")
    return heads[0]


def _ddl(clause: object, dialect: Dialect) -> str:
    """编译单条 DDL —— 注意 compile() 不带分号，必须补上，否则整个文件语句粘连。"""
    return str(clause.compile(dialect=dialect)).strip().rstrip(";") + ";"


def _render(dialect_name: str) -> str:
    """导出该方言的完整 DDL（建表 → 索引 → alembic 版本标记）。"""
    dialect: Dialect = _DIALECTS[dialect_name]()
    lines: list[str] = [_HEADER, f"-- 方言：{dialect_name}", "", "BEGIN;", ""]

    for table in Base.metadata.sorted_tables:
        lines.append(_ddl(CreateTable(table, if_not_exists=True), dialect))
        lines.append("")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            lines.append(_ddl(CreateIndex(index, if_not_exists=True), dialect))
            lines.append("")
        lines.append("")

    lines += [
        "-- ---- alembic 版本标记（导入后 alembic upgrade 不会重复建表）----",
        "CREATE TABLE IF NOT EXISTS alembic_version (",
        "    version_num VARCHAR(32) NOT NULL,",
        "    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)",
        ");",
        "DELETE FROM alembic_version;",
        f"INSERT INTO alembic_version (version_num) VALUES ('{_head_revision()}');",
        "",
        "COMMIT;",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成数据库初始化 SQL（从 ORM 元数据导出）")
    parser.add_argument(
        "--dialect",
        choices=[*_DIALECTS, "all"],
        default="all",
        help="目标方言（默认 all：两个都生成）",
    )
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="输出目录（默认 deploy/sql/）")
    parser.add_argument("--check", action="store_true", help="只校验：产物与当前模型是否一致")
    args = parser.parse_args()

    names = list(_DIALECTS) if args.dialect == "all" else [args.dialect]
    targets = {name: args.out / f"init_{name}.sql" for name in names}

    if args.check:
        stale: list[str] = []
        for name, path in targets.items():
            expected = _render(name)
            actual = path.read_text(encoding="utf-8") if path.exists() else ""
            if actual != expected:
                stale.append(str(path))
                diff = difflib.unified_diff(
                    actual.splitlines(), expected.splitlines(), lineterm="", n=1
                )
                print(f"\n[FAIL] {path} 与当前模型不一致：", file=sys.stderr)
                print("\n".join(list(diff)[:40]), file=sys.stderr)
        if stale:
            print(
                "\n请重新生成：cd backend && uv run python scripts/db_init_sql.py",
                file=sys.stderr,
            )
            return 1
        print("[OK] 初始化 SQL 与当前模型一致")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    for name, path in targets.items():
        sql = _render(name)
        path.write_text(sql, encoding="utf-8", newline="\n")
        print(f"已生成 {path}（{len(sql.splitlines())} 行，{len(Base.metadata.tables)} 张表）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
