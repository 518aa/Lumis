"""SQLite 数据库连接与初始化"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "lumis.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    shibie_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    stars INTEGER NOT NULL DEFAULT 0,
    current_lesson INTEGER NOT NULL DEFAULT 1,
    completed_lessons TEXT NOT NULL DEFAULT '[]',
    mode TEXT NOT NULL DEFAULT 'teaching',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    avatar TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    shibie_id TEXT UNIQUE NOT NULL REFERENCES users(shibie_id),
    device_name TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shibie_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shibie_id TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,
    stars_earned INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'in_progress',
    completed_at TEXT,
    UNIQUE(shibie_id, lesson_number)
);

CREATE INDEX IF NOT EXISTS idx_devices_account ON devices(account_id);
CREATE INDEX IF NOT EXISTS idx_devices_shibie ON devices(shibie_id);
"""

_SEED_DATA = [
    ("test-user", "丽丽", 10, 9, json.dumps([1, 2, 3, 4, 5, 6, 7, 8]), "teaching"),
]


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(_SCHEMA)

        existing = conn.execute(
            "SELECT 1 FROM users WHERE shibie_id = ?", (_SEED_DATA[0][0],)
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO users (shibie_id, name, stars, current_lesson, completed_lessons, mode)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                _SEED_DATA[0],
            )
            conn.commit()
    finally:
        conn.close()
