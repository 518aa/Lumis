"""数据库连接与初始化 — 自动适配 SQLite (本地) / PostgreSQL (生产)"""

import json
import os
import sys

from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Text, Float, UniqueConstraint
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# ── 环境判断 ──────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

print(f"[Lumis DB] IS_POSTGRES={IS_POSTGRES}, URL={'***' + DATABASE_URL[-30:] if DATABASE_URL else 'not set'}")

if IS_POSTGRES:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in DATABASE_URL and "?" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    elif "sslmode" not in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 30},
    )
else:
    from pathlib import Path
    _db_path = Path(__file__).resolve().parent.parent / "lumis.db"
    engine = create_engine(
        f"sqlite:///{_db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

metadata = MetaData()

# ── 表定义 (兼容 SQLite / PostgreSQL) ─────────────────────

users = Table("users", metadata,
    Column("shibie_id", String, primary_key=True),
    Column("name", String, nullable=False, server_default=""),
    Column("stars", Integer, nullable=False, server_default="0"),
    Column("current_lesson", Integer, nullable=False, server_default="1"),
    Column("current_round", Integer, nullable=False, server_default="0"),
    Column("completed_lessons", Text, nullable=False, server_default="[]"),
    Column("mode", String, nullable=False, server_default="teaching"),
    Column("created_at", Text, server_default=""),
    Column("updated_at", Text, server_default=""),
    Column("invite_code", String, server_default=""),
    Column("access_level", String, nullable=False, server_default="free"),
    Column("paid_at", Text),
    Column("torch_points", Integer, server_default="0"),
    Column("total_earnings", Float, server_default="0"),
    Column("available_balance", Float, server_default="0"),
    Column("alipay_account", String, server_default=""),
    Column("real_name", String, server_default=""),
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
    UniqueConstraint("shibie_id", "lesson_number", name="uq_lesson_progress_sid_lesson"),
)

payments = Table("payments", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("shibie_id", String, nullable=False),
    Column("out_trade_no", String, unique=True, nullable=False),
    Column("amount", String, nullable=False, server_default="99"),
    Column("status", String, server_default="pending"),
    Column("channel", String, server_default="alipay"),
    Column("paid_at", Text),
    Column("created_at", Text, server_default=""),
)

invite_codes = Table("invite_codes", metadata,
    Column("code", String(4), primary_key=True),
    Column("owner_shibie_id", String, nullable=False),
    Column("used_count", Integer, server_default="0"),
    Column("created_at", Text, server_default=""),
)

referrals = Table("referrals", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("invite_code", String, nullable=False),
    Column("inviter_shibie_id", String, nullable=False),
    Column("invitee_shibie_id", String, nullable=False),
    Column("created_at", Text, server_default=""),
    UniqueConstraint("invitee_shibie_id", name="uq_referrals_invitee"),
)

earnings = Table("earnings", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("earner_shibie_id", String, nullable=False),
    Column("source_shibie_id", String, nullable=False),
    Column("payment_trade_no", String),
    Column("amount", Float, nullable=False),
    Column("status", String, server_default="pending"),
    Column("created_at", Text, server_default=""),
)

withdrawals = Table("withdrawals", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("shibie_id", String, nullable=False),
    Column("amount", Float, nullable=False),
    Column("status", String, server_default="pending"),
    Column("alipay_account", String, server_default=""),
    Column("real_name", String, server_default=""),
    Column("admin_note", String, server_default=""),
    Column("created_at", Text, server_default=""),
    Column("processed_at", Text),
)

torch_points_log = Table("torch_points_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("shibie_id", String, nullable=False),
    Column("points", Integer, nullable=False),
    Column("reason", String, nullable=False),
    Column("source_type", String, nullable=False),
    Column("source_id", String, server_default=""),
    Column("created_at", Text, server_default=""),
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
    """建表 + 迁移 + 种子数据"""
    metadata.create_all(engine)

    if not IS_POSTGRES:
        _migrate_sqlite_unique_constraint()
        _migrate_sqlite_torch_columns()

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


def _migrate_sqlite_unique_constraint():
    """SQLite 无法 ALTER ADD CONSTRAINT，需重建 lesson_progress 表"""
    with engine.connect() as conn:
        has_constraint = conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='uq_lesson_progress_sid_lesson'"
        )).fetchone()
        if has_constraint:
            return

        conn.execute(text("CREATE TABLE lesson_progress_new ("
                          "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "shibie_id VARCHAR NOT NULL, "
                          "lesson_number INTEGER NOT NULL, "
                          "stars_earned INTEGER DEFAULT 0, "
                          "status VARCHAR DEFAULT 'in_progress', "
                          "completed_at TEXT, "
                          "CONSTRAINT uq_lesson_progress_sid_lesson UNIQUE (shibie_id, lesson_number))"))
        conn.execute(text(
            "INSERT OR IGNORE INTO lesson_progress_new SELECT * FROM lesson_progress"
        ))
        conn.execute(text("DROP TABLE lesson_progress"))
        conn.execute(text("ALTER TABLE lesson_progress_new RENAME TO lesson_progress"))
        conn.commit()


def _migrate_sqlite_torch_columns():
    """SQLite: 为 users 表添加火炬计划新字段"""
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(users)")).fetchall()}
        if "invite_code" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN invite_code VARCHAR DEFAULT ''"))
        if "access_level" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN access_level VARCHAR NOT NULL DEFAULT 'free'"))
        if "paid_at" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN paid_at TEXT"))
        if "torch_points" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN torch_points INTEGER DEFAULT 0"))
        if "total_earnings" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN total_earnings REAL DEFAULT 0"))
        if "available_balance" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN available_balance REAL DEFAULT 0"))
        if "alipay_account" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN alipay_account VARCHAR DEFAULT ''"))
        if "real_name" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN real_name VARCHAR DEFAULT ''"))
        conn.commit()
