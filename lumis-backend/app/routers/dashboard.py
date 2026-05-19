"""火炬计划 — 推广合伙人后台"""

import os

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import (
    get_db, _now, users, payments, invite_codes, referrals,
    earnings, withdrawals, torch_points_log,
)
from app.auth import (
    verify_password, create_access_token, get_current_account_from_cookie,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

WITHDRAWAL_MIN = 100.0
ADMIN_PASSWORD = os.environ.get("LUMIS_ADMIN_PASSWORD", "lumis-admin-2025")


# ── Pydantic Models ─────────────────────────────────────────

class WithdrawBody(BaseModel):
    amount: float

class BindAlipayBody(BaseModel):
    alipay_account: str
    real_name: str


# ── 工具函数 ──────────────────────────────────────────────

def _torch_level(points: int) -> str:
    if points >= 200:
        return "火炬大使"
    if points >= 100:
        return "火炬达人"
    if points >= 50:
        return "火炬先锋"
    if points >= 10:
        return "火炬新手"
    return "等待点亮"


def _get_user_data(db: Session, shibie_id: str) -> dict:
    """聚合查询用户全部 Dashboard 数据"""
    user = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": shibie_id}
    ).fetchone()
    if not user:
        return None

    u = dict(user._mapping)

    # 已邀请人列表（含被邀请人的状态）
    invitees = db.execute(
        text("""
            SELECT r.invitee_shibie_id, r.created_at, u.name,
                   u.access_level, u.current_lesson
            FROM referrals r
            LEFT JOIN users u ON u.shibie_id = r.invitee_shibie_id
            WHERE r.inviter_shibie_id = :sid
            ORDER BY r.created_at DESC
        """), {"sid": shibie_id}
    ).fetchall()

    invitee_list = []
    for row in invitees:
        m = row._mapping
        status = "已注册"
        if m["access_level"] in ("paid",):
            status = "已付费"
        elif m["access_level"] == "invited":
            status = "邀请激活"
        elif m["current_lesson"] and int(m["current_lesson"]) > 1:
            status = "学习中"
        invitee_list.append({
            "name": m["name"] or m["invitee_shibie_id"][:8],
            "created_at": m["created_at"],
            "status": status,
        })

    # 收益明细
    earnings_rows = db.execute(
        text("""
            SELECT e.amount, e.status, e.created_at,
                   u.name as source_name
            FROM earnings e
            LEFT JOIN users u ON u.shibie_id = e.source_shibie_id
            WHERE e.earner_shibie_id = :sid
            ORDER BY e.created_at DESC
            LIMIT 50
        """), {"sid": shibie_id}
    ).fetchall()

    earnings_list = []
    total_withdrawn = 0
    for row in earnings_rows:
        m = row._mapping
        earnings_list.append({
            "source_name": m["source_name"] or "未知用户",
            "amount": m["amount"],
            "status": m["status"],
            "created_at": m["created_at"],
        })

    # 已提现金额
    withdrawn_row = db.execute(
        text("SELECT COALESCE(SUM(amount), 0) as total FROM withdrawals "
             "WHERE shibie_id = :sid AND status IN ('approved', 'paid')"),
        {"sid": shibie_id}
    ).fetchone()
    total_withdrawn = withdrawn_row._mapping["total"] if withdrawn_row else 0

    # 提现记录
    withdrawal_rows = db.execute(
        text("SELECT amount, status, created_at, admin_note FROM withdrawals "
             "WHERE shibie_id = :sid ORDER BY created_at DESC LIMIT 20"),
        {"sid": shibie_id}
    ).fetchall()

    withdrawal_list = []
    for row in withdrawal_rows:
        m = row._mapping
        withdrawal_list.append({
            "amount": m["amount"],
            "status": m["status"],
            "created_at": m["created_at"],
            "admin_note": m["admin_note"] or "",
        })

    # 火炬值日志
    torch_rows = db.execute(
        text("SELECT points, reason, source_type, created_at FROM torch_points_log "
             "WHERE shibie_id = :sid ORDER BY created_at DESC LIMIT 50"),
        {"sid": shibie_id}
    ).fetchall()

    torch_list = []
    for row in torch_rows:
        m = row._mapping
        torch_list.append({
            "points": m["points"],
            "reason": m["reason"],
            "source_type": m["source_type"],
            "created_at": m["created_at"],
        })

    return {
        "user": u,
        "torch_level": _torch_level(u.get("torch_points", 0)),
        "invitees": invitee_list,
        "invitee_count": len(invitee_list),
        "earnings": earnings_list,
        "total_earnings": u.get("total_earnings", 0),
        "available_balance": u.get("available_balance", 0),
        "total_withdrawn": total_withdrawn,
        "withdrawals": withdrawal_list,
        "torch_log": torch_list,
        "torch_points": u.get("torch_points", 0),
    }


# ── 登录页面 ──────────────────────────────────────────────

@router.get("/dashboard/login", response_class=HTMLResponse)
def dashboard_login_page(request: Request):
    return templates.TemplateResponse("dashboard_login.html", {"request": request})


@router.post("/api/web/login")
def web_login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM accounts WHERE email = :email"), {"email": email.strip().lower()}
    ).fetchone()
    if not row or not verify_password(password, row._mapping["password_hash"]):
        return templates.TemplateResponse("dashboard_login.html", {
            "request": request, "error": "邮箱或密码错误"
        })

    account_id = row._mapping["id"]
    token = create_access_token(account_id)

    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie(
        key="access_token", value=token,
        httponly=True, max_age=86400, path="/",
    )
    return resp


@router.post("/api/web/logout")
def web_logout(request: Request):
    resp = RedirectResponse(url="/dashboard/login", status_code=302)
    resp.delete_cookie("access_token", path="/")
    return resp


# ── Dashboard 主页面 ──────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    account = get_current_account_from_cookie(request, db)
    if isinstance(account, RedirectResponse):
        return account

    sid = account.get("shibie_id", "")
    if not sid:
        return templates.TemplateResponse("dashboard.html", {
            "request": request, "account": account, "data": None,
            "error": "未找到关联的学习账号",
        })

    data = _get_user_data(db, sid)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "account": account, "data": data, "error": None,
    })


# ── Dashboard API ─────────────────────────────────────────

@router.post("/api/dashboard/generate-invite")
def generate_invite_api(request: Request, db: Session = Depends(get_db)):
    account = get_current_account_from_cookie(request, db)
    if isinstance(account, RedirectResponse):
        return JSONResponse({"success": False, "error": "未登录"}, status_code=401)

    sid = account.get("shibie_id", "")
    if not sid:
        return {"success": False, "error": "未找到学习账号"}

    import random
    code_chars = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

    existing = db.execute(
        text("SELECT invite_code FROM users WHERE shibie_id = :sid"), {"sid": sid}
    ).fetchone()
    if existing and existing._mapping["invite_code"]:
        return {"success": True, "data": {"code": existing._mapping["invite_code"]}}

    for _ in range(50):
        code = "".join(random.choices(code_chars, k=4))
        exists = db.execute(
            text("SELECT 1 FROM invite_codes WHERE code = :c"), {"c": code}
        ).fetchone()
        if not exists:
            break
    else:
        return {"success": False, "error": "邀请码生成失败"}

    now = _now()
    db.execute(
        text("UPDATE users SET invite_code = :c, updated_at = :now WHERE shibie_id = :sid"),
        {"c": code, "now": now, "sid": sid},
    )
    db.execute(
        invite_codes.insert().values(code=code, owner_shibie_id=sid, created_at=now)
    )
    db.commit()
    return {"success": True, "data": {"code": code}}


@router.post("/api/dashboard/bind-alipay")
def bind_alipay(body: BindAlipayBody, request: Request, db: Session = Depends(get_db)):
    account = get_current_account_from_cookie(request, db)
    if isinstance(account, RedirectResponse):
        return JSONResponse({"success": False, "error": "未登录"}, status_code=401)

    sid = account.get("shibie_id", "")
    if not sid:
        return {"success": False, "error": "未找到学习账号"}

    alipay = body.alipay_account.strip()
    name = body.real_name.strip()
    if not alipay or not name:
        return {"success": False, "error": "支付宝账号和真实姓名不能为空"}

    db.execute(
        text("UPDATE users SET alipay_account = :acc, real_name = :name, updated_at = :now WHERE shibie_id = :sid"),
        {"acc": alipay, "name": name, "now": _now(), "sid": sid},
    )
    db.commit()
    return {"success": True}


@router.post("/api/dashboard/withdraw")
def request_withdrawal(body: WithdrawBody, request: Request, db: Session = Depends(get_db)):
    account = get_current_account_from_cookie(request, db)
    if isinstance(account, RedirectResponse):
        return JSONResponse({"success": False, "error": "未登录"}, status_code=401)

    sid = account.get("shibie_id", "")
    if not sid:
        return {"success": False, "error": "未找到学习账号"}

    user = db.execute(
        text("SELECT available_balance, alipay_account, real_name FROM users WHERE shibie_id = :sid"),
        {"sid": sid},
    ).fetchone()
    if not user:
        return {"success": False, "error": "用户不存在"}

    m = user._mapping
    if m["available_balance"] < WITHDRAWAL_MIN:
        return {"success": False, "error": f"可提现余额不足 ¥{WITHDRAWAL_MIN:.0f}"}

    if not m["alipay_account"] or not m["real_name"]:
        return {"success": False, "error": "请先绑定支付宝账号"}

    amount = body.amount
    if amount < WITHDRAWAL_MIN:
        return {"success": False, "error": f"最低提现 ¥{WITHDRAWAL_MIN:.0f}"}
    if amount > m["available_balance"]:
        return {"success": False, "error": "提现金额超过可提现余额"}

    now = _now()
    db.execute(
        withdrawals.insert().values(
            shibie_id=sid, amount=amount,
            status="pending",
            alipay_account=m["alipay_account"],
            real_name=m["real_name"],
            created_at=now,
        )
    )
    db.execute(
        text("UPDATE users SET available_balance = available_balance - :amt, updated_at = :now WHERE shibie_id = :sid"),
        {"amt": amount, "now": now, "sid": sid},
    )
    db.commit()
    return {"success": True, "data": {"amount": amount, "status": "pending"}}


# ── 管理员 API ────────────────────────────────────────────

def _verify_admin(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] == ADMIN_PASSWORD
    return False


@router.get("/api/admin/withdrawals")
def admin_list_withdrawals(request: Request, db: Session = Depends(get_db)):
    if not _verify_admin(request):
        return JSONResponse({"success": False, "error": "无权限"}, status_code=403)

    rows = db.execute(
        text("""
            SELECT w.id, w.shibie_id, w.amount, w.status, w.alipay_account,
                   w.real_name, w.admin_note, w.created_at, w.processed_at,
                   u.name as user_name
            FROM withdrawals w
            LEFT JOIN users u ON u.shibie_id = w.shibie_id
            ORDER BY w.created_at DESC LIMIT 100
        """)
    ).fetchall()

    items = []
    for row in rows:
        m = row._mapping
        items.append({
            "id": m["id"], "shibie_id": m["shibie_id"],
            "user_name": m["user_name"] or "", "amount": m["amount"],
            "status": m["status"], "alipay_account": m["alipay_account"],
            "real_name": m["real_name"], "admin_note": m["admin_note"],
            "created_at": m["created_at"], "processed_at": m["processed_at"] or "",
        })

    return {"success": True, "data": items}


class ProcessWithdrawBody(BaseModel):
    status: str  # approved / rejected / paid
    admin_note: str = ""

@router.post("/api/admin/withdrawals/{withdrawal_id}/process")
def admin_process_withdrawal(
    withdrawal_id: int, body: ProcessWithdrawBody,
    request: Request, db: Session = Depends(get_db),
):
    if not _verify_admin(request):
        return JSONResponse({"success": False, "error": "无权限"}, status_code=403)

    row = db.execute(
        text("SELECT * FROM withdrawals WHERE id = :id"), {"id": withdrawal_id}
    ).fetchone()
    if not row:
        return {"success": False, "error": "提现记录不存在"}

    if row._mapping["status"] != "pending":
        return {"success": False, "error": "该记录已处理"}

    now = _now()
    db.execute(
        text("UPDATE withdrawals SET status = :status, admin_note = :note, processed_at = :now WHERE id = :id"),
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
