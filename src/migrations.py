# -*- coding: utf-8 -*-
"""极简 SQLite 迁移。

`Base.metadata.create_all()` 只能建新表，改不了已有表的列，
所以字段的增删在这里补一刀。每次应用启动跑一遍，幂等；
任何一步失败都只记日志、不抛异常，避免影响正常使用。
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect

from src.database import engine

log = logging.getLogger(__name__)

# 需要新增的列：(表, 列, 建列时附在列名后的 SQL 片段)
_ADD_COLUMNS = [
    ("students", "school", "VARCHAR(100) NOT NULL DEFAULT ''"),
    ("student_mistakes", "snapshot_analysis", "TEXT NOT NULL DEFAULT ''"),
]

# 已从模型里去掉的旧列：(表, 列)
_DROP_COLUMNS = [
    ("students", "grade"),
]

# 新列建好后需要顺带回填一次的数据（只在「这一列确实是本次新建」时执行）
_BACKFILL_AFTER_ADD = {
    ("student_mistakes", "snapshot_analysis"): (
        "UPDATE student_mistakes SET snapshot_analysis = COALESCE("
        "(SELECT q.analysis FROM questions q "
        " WHERE q.id = student_mistakes.question_id), '') "
        "WHERE snapshot_analysis = ''"
    ),
}


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table: str) -> set[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def run_migrations() -> None:
    """把已有数据库补齐到当前模型的结构。"""
    try:
        with engine.begin() as conn:
            tables = _table_names(conn)

            for table, column, ddl in _ADD_COLUMNS:
                if table not in tables or column in _column_names(conn, table):
                    continue
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
                )
                log.info("migration: %s.%s 已新增", table, column)

                backfill = _BACKFILL_AFTER_ADD.get((table, column))
                if backfill:
                    result = conn.exec_driver_sql(backfill)
                    log.info("migration: %s.%s 回填 %s 行",
                             table, column, result.rowcount)

            for table, column in _DROP_COLUMNS:
                if table not in tables or column not in _column_names(conn, table):
                    continue
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} DROP COLUMN {column}"
                    )
                    log.info("migration: %s.%s 已删除", table, column)
                except Exception:
                    # SQLite < 3.35 或该列被索引占用：留着不用即可，不影响功能
                    log.warning("migration: 无法删除 %s.%s，已跳过", table, column)
    except Exception as exc:  # 迁移失败不应阻断应用启动
        log.warning("migration 失败：%s", exc)


__all__ = ["run_migrations"]
