"""管理后台 — 路由 + 页面渲染"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db, _now, payments, withdrawals
from app.auth import ADMIN_PASSWORD, create_admin_token, get_current_admin

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


# ── Pydantic Models ─────────────────────────────────────────

class UpdateUserBody(BaseModel):
    field: str
    value: str | int


class ProcessWithdrawalBody(BaseModel):
    status: str
    admin_note: str = ""


# ── 登录 ────────────────────────────────────────────────────

@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@router.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "error": "密码错误"
        })

    token = create_admin_token()
    resp = RedirectResponse(url="/admin", status_code=302)
    resp.set_cookie(
        key="admin_token", value=token,
        httponly=True, secure=True, samesite="lax",
        max_age=86400, path="/",
    )
    return resp


@router.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin/login", status_code=302)
    resp.delete_cookie("admin_token", path="/", secure=True, samesite="lax")
    return resp


# ── 概览仪表板 ──────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
def admin_overview(request: Request, db: Session = Depends(get_db)):
    auth = get_current_admin(request)
    if isinstance(auth, RedirectResponse):
        return auth

    total_users = db.execute(text("SELECT COUNT(*) as c FROM users")).fetchone()._mapping["c"]
    paid_users = db.execute(
        text("SELECT COUNT(*) as c FROM users WHERE access_level IN ('paid','invited')")
    ).fetchone()._mapping["c"]
    total_revenue = db.execute(
        text("SELECT COALESCE(SUM(CAST(amount AS FLOAT)),0) as s FROM payments WHERE status='paid'")
    ).fetchone()._mapping["s"]
    pending_withdrawals = db.execute(
        text("SELECT COUNT(*) as c FROM withdrawals WHERE status='pending'")
    ).fetchone()._mapping["c"]

    recent_logs = db.execute(text("""
        SELECT shibie_id, action, payload, created_at FROM sync_logs
        ORDER BY created_at DESC LIMIT 15
    """)).fetchall()

    recent_payments = db.execute(text("""
        SELECT p.out_trade_no, p.amount, p.status, p.created_at, u.name
        FROM payments p LEFT JOIN users u ON u.shibie_id = p.shibie_id
        ORDER BY p.created_at DESC LIMIT 10
    """)).fetchall()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "stats": {
            "total_users": total_users,
            "paid_users": paid_users,
            "total_revenue": total_revenue,
            "pending_withdrawals": pending_withdrawals,
        },
        "recent_logs": [dict(r._mapping) for r in recent_logs],
        "recent_payments": [dict(r._mapping) for r in recent_payments],
    })


# ── 用户管理 ────────────────────────────────────────────────

@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    auth = get_current_admin(request)
    if isinstance(auth, RedirectResponse):
        return auth

    page = max(1, page)
    per_page = 30
    offset = (page - 1) * per_page

    if q:
        count_row = db.execute(text(
            "SELECT COUNT(*) as c FROM users WHERE name LIKE :q OR shibie_id LIKE :q"
        ), {"q": f"%{q}%"}).fetchone()
        rows = db.execute(text(
            "SELECT * FROM users WHERE name LIKE :q OR shibie_id LIKE :q ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ), {"q": f"%{q}%", "limit": per_page, "offset": offset}).fetchall()
    else:
        count_row = db.execute(text("SELECT COUNT(*) as c FROM users")).fetchone()
        rows = db.execute(text(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ), {"limit": per_page, "offset": offset}).fetchall()

    total = count_row._mapping["c"]
    total_pages = max(1, (total + per_page - 1) // per_page)

    users_list = []
    for r in rows:
        u = dict(r._mapping)
        u["completed_lessons"] = json.loads(u["completed_lessons"]) if isinstance(u.get("completed_lessons"), str) else u.get("completed_lessons", [])
        users_list.append(u)

    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users_list,
        "q": q,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.get("/admin/users/{shibie_id}")
def admin_user_detail(shibie_id: str, db: Session = Depends(get_db)):
    user = db.execute(text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": shibie_id}).fetchone()
    if not user:
        return {"success": False, "error": "用户不存在"}

    u = dict(user._mapping)
    u["completed_lessons"] = json.loads(u["completed_lessons"]) if isinstance(u.get("completed_lessons"), str) else u.get("completed_lessons", [])

    # 邀请关系
    ref = db.execute(text(
        "SELECT r.*, u.name as inviter_name FROM referrals r LEFT JOIN users u ON u.shibie_id = r.inviter_shibie_id WHERE r.invitee_shibie_id = :sid"
    ), {"sid": shibie_id}).fetchone()
    u["referral"] = dict(ref._mapping) if ref else None

    # 收益明细
    earnings_rows = db.execute(text(
        "SELECT e.*, u.name as source_name FROM earnings e LEFT JOIN users u ON u.shibie_id = e.source_shibie_id WHERE e.earner_shibie_id = :sid ORDER BY e.created_at DESC LIMIT 20"
    ), {"sid": shibie_id}).fetchall()
    u["earnings"] = [dict(r._mapping) for r in earnings_rows]

    # 火炬值日志
    torch_rows = db.execute(text(
        "SELECT * FROM torch_points_log WHERE shibie_id = :sid ORDER BY created_at DESC LIMIT 20"
    ), {"sid": shibie_id}).fetchall()
    u["torch_log"] = [dict(r._mapping) for r in torch_rows]

    # 关联邮箱
    device = db.execute(text(
        "SELECT a.email FROM devices d JOIN accounts a ON a.id = d.account_id WHERE d.shibie_id = :sid AND d.is_active = 1 LIMIT 1"
    ), {"sid": shibie_id}).fetchone()
    u["email"] = device._mapping["email"] if device else ""

    return {"success": True, "data": u}


@router.post("/admin/users/{shibie_id}/update")
def admin_update_user(shibie_id: str, body: UpdateUserBody, request: Request, db: Session = Depends(get_db)):
    auth = get_current_admin(request)
    if isinstance(auth, RedirectResponse):
        return JSONResponse({"success": False, "error": "未登录"}, status_code=401)

    allowed_fields = {"access_level", "stars", "current_lesson", "name", "mode"}
    if body.field not in allowed_fields:
        return {"success": False, "error": f"不允许修改字段: {body.field}"}

    value = body.value
    if body.field in ("stars", "current_lesson"):
        try:
            value = int(value)
        except ValueError:
            return {"success": False, "error": "值必须是整数"}

    db.execute(
        text(f"UPDATE users SET {body.field} = :val, updated_at = :now WHERE shibie_id = :sid"),
        {"val": value, "now": _now(), "sid": shibie_id},
    )
    db.commit()
    return {"success": True}


# ── 支付记录 ────────────────────────────────────────────────

@router.get("/admin/payments", response_class=HTMLResponse)
def admin_payments_page(request: Request, status: str = "", page: int = 1, db: Session = Depends(get_db)):
    auth = get_current_admin(request)
    if isinstance(auth, RedirectResponse):
        return auth

    page = max(1, page)
    per_page = 30
    offset = (page - 1) * per_page

    if status in ("pending", "paid"):
        count_row = db.execute(text(
            "SELECT COUNT(*) as c FROM payments WHERE status = :status"
        ), {"status": status}).fetchone()
        rows = db.execute(text("""
            SELECT p.*, u.name FROM payments p
            LEFT JOIN users u ON u.shibie_id = p.shibie_id
            WHERE p.status = :status ORDER BY p.created_at DESC LIMIT :limit OFFSET :offset
        """), {"status": status, "limit": per_page, "offset": offset}).fetchall()
    else:
        count_row = db.execute(text("SELECT COUNT(*) as c FROM payments")).fetchone()
        rows = db.execute(text("""
            SELECT p.*, u.name FROM payments p
            LEFT JOIN users u ON u.shibie_id = p.shibie_id
            ORDER BY p.created_at DESC LIMIT :limit OFFSET :offset
        """), {"limit": per_page, "offset": offset}).fetchall()

    total = count_row._mapping["c"]
    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse("admin_payments.html", {
        "request": request,
        "payments": [dict(r._mapping) for r in rows],
        "status": status,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.post("/admin/payments/{order_id}/mark-paid")
def admin_mark_paid(order_id: str, request: Request, db: Session = Depends(get_db)):
    auth = get_current_admin(request)
    if isinstance(auth, RedirectResponse):
        return JSONResponse({"success": False, "error": "未登录"}, status_code=401)

    row = db.execute(text("SELECT * FROM payments WHERE out_trade_no = :no"), {"no": order_id}).fetchone()
    if not row:
        return {"success": False, "error": "订单不存在"}
    if row._mapping["status"] == "paid":
        return {"success": False, "error": "订单已支付"}

    sid = row._mapping["shibie_id"]
    now = _now()
    db.execute(text("UPDATE payments SET status='paid', paid_at=:now WHERE out_trade_no=:no"), {"now": now, "no": order_id})
    db.execute(text("UPDATE users SET access_level='paid', paid_at=:now, updated_at=:now WHERE shibie_id=:sid"), {"now": now, "sid": sid})
    db.commit()
    return {"success": True}


# ── 提现审批 ────────────────────────────────────────────────

@router.get("/admin/withdrawals", response_class=HTMLResponse)
def admin_withdrawals_page(request: Request, status: str = "", page: int = 1, db: Session = Depends(get_db)):
    auth = get_current_admin(request)
    if isinstance(auth, RedirectResponse):
        return auth

    page = max(1, page)
    per_page = 30
    offset = (page - 1) * per_page

    valid_statuses = ("pending", "approved", "rejected", "paid")
    if status in valid_statuses:
        count_row = db.execute(text(
            "SELECT COUNT(*) as c FROM withdrawals WHERE status = :status"
        ), {"status": status}).fetchone()
        rows = db.execute(text("""
            SELECT w.*, u.name FROM withdrawals w
            LEFT JOIN users u ON u.shibie_id = w.shibie_id
            WHERE w.status = :status ORDER BY w.created_at DESC LIMIT :limit OFFSET :offset
        """), {"status": status, "limit": per_page, "offset": offset}).fetchall()
    else:
        count_row = db.execute(text("SELECT COUNT(*) as c FROM withdrawals")).fetchone()
        rows = db.execute(text("""
            SELECT w.*, u.name FROM withdrawals w
            LEFT JOIN users u ON u.shibie_id = w.shibie_id
            ORDER BY w.created_at DESC LIMIT :limit OFFSET :offset
        """), {"limit": per_page, "offset": offset}).fetchall()

    total = count_row._mapping["c"]
    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse("admin_withdrawals.html", {
        "request": request,
        "withdrawals": [dict(r._mapping) for r in rows],
        "status": status,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.post("/admin/withdrawals/{withdrawal_id}/process")
def admin_process_withdrawal(
    withdrawal_id: int, body: ProcessWithdrawalBody,
    request: Request, db: Session = Depends(get_db),
):
    auth = get_current_admin(request)
    if isinstance(auth, RedirectResponse):
        return JSONResponse({"success": False, "error": "未登录"}, status_code=401)

    row = db.execute(text("SELECT * FROM withdrawals WHERE id = :id"), {"id": withdrawal_id}).fetchone()
    if not row:
        return {"success": False, "error": "提现记录不存在"}
    if row._mapping["status"] != "pending":
        return {"success": False, "error": "该记录已处理"}

    now = _now()
    db.execute(
        text("UPDATE withdrawals SET status=:status, admin_note=:note, processed_at=:now WHERE id=:id"),
        {"status": body.status, "note": body.admin_note, "now": now, "id": withdrawal_id},
    )

    if body.status == "rejected":
        sid = row._mapping["shibie_id"]
        amount = row._mapping["amount"]
        db.execute(
            text("UPDATE users SET available_balance = available_balance + :amt WHERE shibie_id = :sid"),
            {"amt": amount, "sid": sid},
        )

    db.commit()
    return {"success": True}
