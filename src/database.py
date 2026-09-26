# -*- coding: utf-8 -*-
"""数据库引擎 / 会话 / 初始化。"""
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import DB_URL


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


# SQLite 在多线程（Streamlit 会开线程）下需要 check_same_thread=False
engine = create_engine(
    DB_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _record):
    """SQLite 默认不开外键约束，这里手动打开，保证级联删除正常。"""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def get_session():
    """返回一个新 Session，调用方负责 close()。"""
    return SessionLocal()


@contextmanager
def session_scope():
    """推荐用法：with session_scope() as s: ... 自动提交/回滚/关闭。"""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db():
    """建表（已存在则跳过）。应用启动时调用一次。"""
    from src import models  # noqa: F401  导入以注册所有模型
    Base.metadata.create_all(engine)