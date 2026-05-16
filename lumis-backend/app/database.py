"""数据库连接与初始化 — 自动适配 SQLite (本地) / PostgreSQL (生产)"""

import json
import os

from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Text
from sqlalchemy.orm import Session

# ── 环境判断 ──────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

if IS_POSTGRES:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    from pathlib import Path
    _db_path = Path(__file__).resolve().parent.parent / "lumis.db"
    engine = create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})

metadata = MetaData()

# ── 表定义 (兼容 SQLite / PostgreSQL) ─────────────────────

users = Table("users", metadata,
    Column("shibie_id", String, primary_key=True),
    Column("name", String, nullable=False, server_default=""),
    Column("stars", Integer, nullable=False, server_default="0"),
    Column("current_lesson", Integer, nullable=False, server_default="1"),
    Column("completed_lessons", Text, nullable=False, server_default="[]"),
    Column("mode", String, nullable=False, server_default="teaching"),
    Column("created_at", Text, server_default=""),
    Column("updated_at", Text, server_default=""),
)

accounts = Table("accounts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String, unique=True, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("username", String, server_default=""),
    Column("avatar", String, server_default=""),
    Column("created_at", Text, server_default=""),
    Column("updated_at", Text, server_default=""),
)

devices = Table("devices", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", Integer, nullable=False),
    Column("shibie_id", String, unique=True),
    Column("device_name", String, server_default=""),
    Column("is_active", Integer, server_default="1"),
    Column("created_at", Text, server_default=""),
)

sync_logs = Table("sync_logs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("shibie_id", String, nullable=False),
    Column("action", String, nullable=False),
    Column("payload", Text, server_default="{}"),
    Column("created_at", Text, server_default=""),
)

lesson_progress = Table("lesson_progress", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("shibie_id", String, nullable=False),
    Column("lesson_number", Integer, nullable=False),
    Column("stars_earned", Integer, server_default="0"),
    Column("status", String, server_default="in_progress"),
    Column("completed_at", Text),
)

# ── 辅助函数 ──────────────────────────────────────────────

def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    """FastAPI Depends: 返回 SQLAlchemy Session"""
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def init_db():
    """建表 + 种子数据"""
    metadata.create_all(engine)

    with Session(engine) as session:
        existing = session.execute(
            text("SELECT 1 FROM users WHERE shibie_id = :sid"), {"sid": "test-user"}
        ).fetchone()
        if not existing:
            session.execute(users.insert().values(
                shibie_id="test-user", name="丽丽", stars=10,
                current_lesson=9,
                completed_lessons=json.dumps([1, 2, 3, 4, 5, 6, 7, 8]),
                mode="teaching",
                created_at=_now(), updated_at=_now(),
            ))
            session.commit()
