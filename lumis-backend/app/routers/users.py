"""用户 API 路由 — 对外（App）+ 内部（MCP）"""

import json
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import get_db

router = APIRouter()


# ── 请求模型 ──────────────────────────────────────────────

class EnsureUserBody(BaseModel):
    shibie_id: str
    name: str = ""


class AddStarsBody(BaseModel):
    shibie_id: str
    count: int = 1


class CompleteLessonBody(BaseModel):
    shibie_id: str
    lesson_number: int


class SwitchModeBody(BaseModel):
    shibie_id: str
    mode: str


# ── 辅助函数 ──────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    """将 sqlite3.Row 转为可序列化字典"""
    d = dict(row)
    d["completed_lessons"] = json.loads(d["completed_lessons"])
    return d


def _write_sync_log(conn, shibie_id: str, action: str, payload: dict):
    conn.execute(
        "INSERT INTO sync_logs (shibie_id, action, payload) VALUES (?, ?, ?)",
        (shibie_id, action, json.dumps(payload, ensure_ascii=False)),
    )


def _ok(data=None):
    return {"success": True, "data": data}


def _err(msg: str):
    return {"success": False, "error": msg}


# ── 对外 API（App 调用）───────────────────────────────────

@router.get("/user/lookup/{query}")
def lookup_user(query: str, db=Depends(get_db)):
    """按昵称或 shibie_id 前缀模糊查找用户（MCP fallback 用）"""
    row = db.execute(
        "SELECT * FROM users WHERE name = ? OR shibie_id LIKE ? LIMIT 1",
        (query, f"{query}%"),
    ).fetchone()
    if not row:
        return _err("用户不存在")
    return _ok(_row_to_dict(row))


@router.get("/user/{shibie_id}")
def get_user(shibie_id: str, db=Depends(get_db)):
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (shibie_id,)
    ).fetchone()
    if not row:
        return _err("用户不存在")
    return _ok(_row_to_dict(row))


@router.post("/user/ensure")
def ensure_user(body: EnsureUserBody, db=Depends(get_db)):
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
    ).fetchone()

    if row:
        if body.name:
            db.execute(
                "UPDATE users SET name = ?, updated_at = datetime('now') WHERE shibie_id = ?",
                (body.name, body.shibie_id),
            )
            db.commit()
            row = db.execute(
                "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
            ).fetchone()
        return _ok(_row_to_dict(row))

    db.execute(
        """INSERT INTO users (shibie_id, name)
           VALUES (?, ?)""",
        (body.shibie_id, body.name),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
    ).fetchone()
    return _ok(_row_to_dict(row))


# ── 内部 API（MCP 调用）───────────────────────────────────

@router.post("/internal/add-stars")
def add_stars(body: AddStarsBody, db=Depends(get_db)):
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
    ).fetchone()
    if not row:
        return _err("用户不存在")

    new_stars = row["stars"] + body.count
    db.execute(
        "UPDATE users SET stars = ?, updated_at = datetime('now') WHERE shibie_id = ?",
        (new_stars, body.shibie_id),
    )
    _write_sync_log(db, body.shibie_id, "add_stars", {"count": body.count, "new_total": new_stars})
    db.commit()
    return _ok({"stars": new_stars})


@router.post("/internal/complete-lesson")
def complete_lesson(body: CompleteLessonBody, db=Depends(get_db)):
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
    ).fetchone()
    if not row:
        return _err("用户不存在")

    completed = json.loads(row["completed_lessons"])
    if body.lesson_number not in completed:
        completed.append(body.lesson_number)

    next_lesson = max(row["current_lesson"], body.lesson_number + 1)

    db.execute(
        """UPDATE users
           SET completed_lessons = ?, current_lesson = ?, updated_at = datetime('now')
           WHERE shibie_id = ?""",
        (json.dumps(completed), next_lesson, body.shibie_id),
    )

    db.execute(
        """INSERT INTO lesson_progress (shibie_id, lesson_number, status, completed_at)
           VALUES (?, ?, 'completed', datetime('now'))
           ON CONFLICT(shibie_id, lesson_number)
           DO UPDATE SET status='completed', completed_at=datetime('now')""",
        (body.shibie_id, body.lesson_number),
    )

    _write_sync_log(db, body.shibie_id, "complete_lesson", {"lesson_number": body.lesson_number})
    db.commit()
    return _ok({"completed_lessons": completed, "current_lesson": next_lesson})


@router.post("/internal/switch-mode")
def switch_mode(body: SwitchModeBody, db=Depends(get_db)):
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
    ).fetchone()
    if not row:
        return _err("用户不存在")

    db.execute(
        "UPDATE users SET mode = ?, updated_at = datetime('now') WHERE shibie_id = ?",
        (body.mode, body.shibie_id),
    )
    _write_sync_log(db, body.shibie_id, "switch_mode", {"mode": body.mode})
    db.commit()
    return _ok({"mode": body.mode})


@router.get("/internal/user-state/{shibie_id}")
def get_user_state(shibie_id: str, db=Depends(get_db)):
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (shibie_id,)
    ).fetchone()
    if not row:
        return _err("用户不存在")
    return _ok(_row_to_dict(row))


class SetLessonBody(BaseModel):
    shibie_id: str
    lesson_number: int


@router.post("/internal/set-lesson")
def set_lesson(body: SetLessonBody, db=Depends(get_db)):
    """直接设置当前课次（跳课用），不修改已完成列表"""
    if not 1 <= body.lesson_number <= 120:
        return _err("课次超出范围 1-120")
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
    ).fetchone()
    if not row:
        return _err("用户不存在")
    db.execute(
        "UPDATE users SET current_lesson = ?, updated_at = datetime('now') WHERE shibie_id = ?",
        (body.lesson_number, body.shibie_id),
    )
    _write_sync_log(db, body.shibie_id, "set_lesson", {"lesson_number": body.lesson_number})
    db.commit()
    return _ok({"current_lesson": body.lesson_number})


class UpdateNameBody(BaseModel):
    shibie_id: str
    name: str


@router.post("/internal/update-name")
def update_name(body: UpdateNameBody, db=Depends(get_db)):
    """更新用户昵称（MCP 调用）"""
    if not body.name.strip():
        return _err("名字不能为空")
    row = db.execute(
        "SELECT * FROM users WHERE shibie_id = ?", (body.shibie_id,)
    ).fetchone()
    if not row:
        return _err("用户不存在")
    db.execute(
        "UPDATE users SET name = ?, updated_at = datetime('now') WHERE shibie_id = ?",
        (body.name.strip(), body.shibie_id),
    )
    _write_sync_log(db, body.shibie_id, "update_name", {"name": body.name.strip()})
    db.commit()
    return _ok({"name": body.name.strip()})
