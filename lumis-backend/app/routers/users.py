"""用户 API 路由 — 对外（App）+ 内部（MCP）"""

import json
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.database import get_db, _now, torch_points_log

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
    d = dict(row._mapping)
    d["completed_lessons"] = json.loads(d["completed_lessons"])
    return d


def _write_sync_log(session, shibie_id: str, action: str, payload: dict):
    session.execute(
        text("INSERT INTO sync_logs (shibie_id, action, payload, created_at) VALUES (:sid, :action, :payload, :now)"),
        {"sid": shibie_id, "action": action, "payload": json.dumps(payload, ensure_ascii=False), "now": _now()},
    )


def _ok(data=None):
    return {"success": True, "data": data}


def _err(msg: str):
    return {"success": False, "error": msg}


# ── 对外 API（App 调用）───────────────────────────────────

@router.get("/user/lookup/{query}")
def lookup_user(query: str, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM users WHERE name = :name OR shibie_id LIKE :sid LIMIT 1"),
        {"name": query, "sid": f"{query}%"},
    ).fetchone()
    if not row:
        return _err("用户不存在")
    return _ok(_row_to_dict(row))


@router.get("/user/{shibie_id}")
def get_user(shibie_id: str, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")
    return _ok(_row_to_dict(row))


@router.post("/user/ensure")
def ensure_user(body: EnsureUserBody, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()

    if row:
        if body.name:
            db.execute(
                text("UPDATE users SET name = :name, updated_at = :now WHERE shibie_id = :sid"),
                {"name": body.name, "now": _now(), "sid": body.shibie_id},
            )
            db.commit()
            row = db.execute(
                text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
            ).fetchone()
        return _ok(_row_to_dict(row))

    db.execute(
        text("INSERT INTO users (shibie_id, name, created_at, updated_at) VALUES (:sid, :name, :now, :now)"),
        {"sid": body.shibie_id, "name": body.name, "now": _now()},
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()
    return _ok(_row_to_dict(row))


# ── 内部 API（MCP 调用）───────────────────────────────────

@router.post("/internal/add-stars")
def add_stars(body: AddStarsBody, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")

    new_stars = row._mapping["stars"] + body.count
    db.execute(
        text("UPDATE users SET stars = :stars, updated_at = :now WHERE shibie_id = :sid"),
        {"stars": new_stars, "now": _now(), "sid": body.shibie_id},
    )
    _write_sync_log(db, body.shibie_id, "add_stars", {"count": body.count, "new_total": new_stars})
    db.commit()
    return _ok({"stars": new_stars})


@router.post("/internal/complete-lesson")
def complete_lesson(body: CompleteLessonBody, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")

    completed = json.loads(row._mapping["completed_lessons"])
    if body.lesson_number not in completed:
        completed.append(body.lesson_number)

    next_lesson = max(row._mapping["current_lesson"], body.lesson_number + 1)

    db.execute(
        text("""UPDATE users
           SET completed_lessons = :completed, current_lesson = :next_lesson, current_round = 0, updated_at = :now
           WHERE shibie_id = :sid"""),
        {"completed": json.dumps(completed), "next_lesson": next_lesson, "now": _now(), "sid": body.shibie_id},
    )

    now = _now()
    db.execute(
        text("""INSERT INTO lesson_progress (shibie_id, lesson_number, status, completed_at)
           VALUES (:sid, :lesson_num, 'completed', :now)
           ON CONFLICT(shibie_id, lesson_number)
           DO UPDATE SET status='completed', completed_at=:now"""),
        {"sid": body.shibie_id, "lesson_num": body.lesson_number, "now": now},
    )

    _write_sync_log(db, body.shibie_id, "complete_lesson", {"lesson_number": body.lesson_number})

    # ── 被邀请人首节课完成：邀请人火炬值 +5 ──
    if body.lesson_number == 1:
        ref = db.execute(
            text("SELECT inviter_shibie_id FROM referrals WHERE invitee_shibie_id = :sid"),
            {"sid": body.shibie_id},
        ).fetchone()
        if ref:
            inviter_sid = ref._mapping["inviter_shibie_id"]
            db.execute(
                text("UPDATE users SET torch_points = torch_points + 5, updated_at = :now WHERE shibie_id = :sid"),
                {"now": now, "sid": inviter_sid},
            )
            db.execute(
                torch_points_log.insert().values(
                    shibie_id=inviter_sid, points=5,
                    reason="被邀请人完成首节课",
                    source_type="lesson", source_id=body.shibie_id,
                    created_at=now,
                )
            )

    db.commit()
    return _ok({"completed_lessons": completed, "current_lesson": next_lesson})


@router.post("/internal/switch-mode")
def switch_mode(body: SwitchModeBody, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")

    db.execute(
        text("UPDATE users SET mode = :mode, updated_at = :now WHERE shibie_id = :sid"),
        {"mode": body.mode, "now": _now(), "sid": body.shibie_id},
    )
    _write_sync_log(db, body.shibie_id, "switch_mode", {"mode": body.mode})
    db.commit()
    return _ok({"mode": body.mode})


@router.get("/internal/user-state/{shibie_id}")
def get_user_state(shibie_id: str, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")
    return _ok(_row_to_dict(row))


class SetRoundBody(BaseModel):
    shibie_id: str
    round_number: int


class SetLessonBody(BaseModel):
    shibie_id: str
    lesson_number: int


@router.post("/internal/set-round")
def set_round(body: SetRoundBody, db=Depends(get_db)):
    if not 0 <= body.round_number <= 3:
        return _err("轮次超出范围 0-3")
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")
    db.execute(
        text("UPDATE users SET current_round = :round, updated_at = :now WHERE shibie_id = :sid"),
        {"round": body.round_number, "now": _now(), "sid": body.shibie_id},
    )
    _write_sync_log(db, body.shibie_id, "set_round", {"round_number": body.round_number})
    db.commit()
    return _ok({"current_round": body.round_number})


@router.post("/internal/set-lesson")
def set_lesson(body: SetLessonBody, db=Depends(get_db)):
    if not 1 <= body.lesson_number <= 120:
        return _err("课次超出范围 1-120")
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")
    db.execute(
        text("UPDATE users SET current_lesson = :lesson, updated_at = :now WHERE shibie_id = :sid"),
        {"lesson": body.lesson_number, "now": _now(), "sid": body.shibie_id},
    )
    _write_sync_log(db, body.shibie_id, "set_lesson", {"lesson_number": body.lesson_number})
    db.commit()
    return _ok({"current_lesson": body.lesson_number})


class UpdateNameBody(BaseModel):
    shibie_id: str
    name: str


@router.post("/internal/update-name")
def update_name(body: UpdateNameBody, db=Depends(get_db)):
    if not body.name.strip():
        return _err("名字不能为空")
    row = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": body.shibie_id}
    ).fetchone()
    if not row:
        return _err("用户不存在")
    db.execute(
        text("UPDATE users SET name = :name, updated_at = :now WHERE shibie_id = :sid"),
        {"name": body.name.strip(), "now": _now(), "sid": body.shibie_id},
    )
    _write_sync_log(db, body.shibie_id, "update_name", {"name": body.name.strip()})
    db.commit()
    return _ok({"name": body.name.strip()})
