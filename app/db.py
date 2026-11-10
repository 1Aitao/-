# -*- coding: utf-8 -*-
"""SQLite 元数据存储。

元数据与文件本体分离存储（术语见 PRD 1.3）：本模块只负责目录结构与文件记录，
文件二进制内容落盘在 data/storage/ 下，以随机存储名隔离（见 security.py）。
"""
import os
import sqlite3
import threading

from . import config

# SQLite 连接按需创建；RLock 可重入，允许事务上下文内嵌套调用 query/execute
_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT    NOT NULL CHECK (type IN ('file', 'folder')),
    name        TEXT    NOT NULL,
    parent_id   INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    stored_name TEXT,                -- 文件本体在 storage/ 下的随机存储名，文件夹为 NULL
    size        INTEGER NOT NULL DEFAULT 0,
    mime        TEXT    NOT NULL DEFAULT 'application/octet-stream',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_parent_name ON nodes(parent_id, name);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
"""


def get_conn() -> sqlite3.Connection:
    """获取全局连接，首次调用时初始化库表与数据目录。"""
    global _conn
    if _conn is None:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        os.makedirs(config.STORAGE_DIR, exist_ok=True)
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def query(sql: str, params=()) -> list:
    """执行只读查询，返回行列表。"""
    with _lock:
        cur = get_conn().execute(sql, params)
        return cur.fetchall()


def execute(sql: str, params=()) -> int:
    """执行单条写操作，返回 lastrowid。失败时回滚，避免遗留打开事务锁死连接。"""
    with _lock:
        try:
            cur = get_conn().execute(sql, params)
            get_conn().commit()
            return cur.lastrowid
        except Exception:
            get_conn().rollback()
            raise


class transaction:
    """多对象变更的事务上下文：全部成功才提交，任一失败整体回滚（PRD 4.2 操作一致性）。"""

    def __enter__(self):
        _lock.acquire()
        return get_conn()

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                get_conn().commit()
            else:
                get_conn().rollback()
        finally:
            _lock.release()
        return False


def row_to_dict(row) -> dict:
    return dict(row) if row is not None else None
