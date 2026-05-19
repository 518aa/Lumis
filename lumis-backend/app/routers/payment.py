"""火炬计划 — 支付宝当面付 + 邀请码 API"""

import io
import os
import random
import string
import base64
import urllib.parse

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import (
    get_db, _now, users, payments, invite_codes, referrals,
    earnings, torch_points_log, IS_POSTGRES,
)

router = APIRouter()

CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

PAYMENT_SUBJECT = "Lumis 儿童英语 — 解锁全部120节课程"
PAYMENT_AMOUNT = "99.00"
PAYMENT_TIMEOUT = "30m"
EARNING_RATE = 0.5  # 推广人分成比例
EARNING_AMOUNT = round(float(PAYMENT_AMOUNT) * EARNING_RATE, 2)  # 49.50


# ── Pydantic Models ─────────────────────────────────────────

class CreatePaymentBody(BaseModel):
    shibie_id: str

class ValidateInviteBody(BaseModel):
    code: str
    shibie_id: str


# ── 邀请码 ──────────────────────────────────────────────────

def _generate_code(db: Session) -> str:
    for _ in range(50):
        code = "".join(random.choices(CODE_CHARS, k=4))
        exists = db.execute(
            text("SELECT 1 FROM invite_codes WHERE code = :c"), {"c": code}
        ).fetchone()
        if not exists:
            return code
    raise RuntimeError("邀请码生成失败：空间不足")


@router.post("/invite/generate/{shibie_id}")
def generate_invite_code(shibie_id: str, db: Session = Depends(get_db)):
    user = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": shibie_id}
    ).fetchone()
    if not user:
        return {"success": False, "error": "用户不存在"}

    existing_code = user._mapping.get("invite_code", "")
    if existing_code:
        return {"success": True, "data": {"code": existing_code}}

    code = _generate_code(db)
    db.execute(
        text("UPDATE users SET invite_code = :c, updated_at = :now WHERE shibie_id = :sid"),
        {"c": code, "now": _now(), "sid": shibie_id},
    )
    db.execute(
        invite_codes.insert().values(
            code=code, owner_shibie_id=shibie_id, created_at=_now()
        )
    )
    db.commit()
    return {"success": True, "data": {"code": code}}


@router.post("/invite/validate")
def validate_invite_code(body: ValidateInviteBody, db: Session = Depends(get_db)):
    code = body.code.strip().upper()
    sid = body.shibie_id.strip()

    if not code or not sid:
        return {"success": False, "error": "参数不完整"}

    row = db.execute(
        text("SELECT * FROM invite_codes WHERE code = :c"), {"c": code}
    ).fetchone()
    if not row:
        return {"success": False, "error": "邀请码无效"}

    owner = row._mapping["owner_shibie_id"]
    if owner == sid:
        return {"success": False, "error": "不能使用自己的邀请码"}

    user = db.execute(
        text("SELECT * FROM users WHERE shibie_id = :sid"), {"sid": sid}
    ).fetchone()
    if not user:
        return {"success": False, "error": "用户不存在"}

    if user._mapping["access_level"] in ("paid", "invited"):
        return {"success": False, "error": "已有完整权限，无需激活"}

    existing_ref = db.execute(
        text("SELECT 1 FROM referrals WHERE invitee_shibie_id = :sid"), {"sid": sid}
    ).fetchone()
    if existing_ref:
        return {"success": False, "error": "已使用过邀请码"}

    db.execute(
        text("UPDATE users SET access_level = 'invited', updated_at = :now WHERE shibie_id = :sid"),
        {"now": _now(), "sid": sid},
    )
    db.execute(
        referrals.insert().values(
            invite_code=code, inviter_shibie_id=owner,
            invitee_shibie_id=sid, created_at=_now(),
        )
    )
    db.execute(
        text("UPDATE invite_codes SET used_count = used_count + 1 WHERE code = :c"),
        {"c": code},
    )

    # ── 邀请人火炬值 +10 ──
    now = _now()
    db.execute(
        text("UPDATE users SET torch_points = torch_points + 10, updated_at = :now WHERE shibie_id = :sid"),
        {"now": now, "sid": owner},
    )
    db.execute(
        torch_points_log.insert().values(
            shibie_id=owner, points=10,
            reason="成功邀请用户注册",
            source_type="invite", source_id=sid,
            created_at=now,
        )
    )

    db.commit()
    return {"success": True, "data": {"access_level": "invited"}}


# ── 访问权限 ────────────────────────────────────────────────

@router.get("/access/status/{shibie_id}")
def get_access_status(shibie_id: str, db: Session = Depends(get_db)):
    user = db.execute(
        text("SELECT access_level, current_lesson FROM users WHERE shibie_id = :sid"),
        {"sid": shibie_id},
    ).fetchone()
    if not user:
        return {"success": False, "error": "用户不存在"}

    level = user._mapping["access_level"]
    lesson = user._mapping["current_lesson"]

    if level in ("paid", "invited"):
        return {"success": True, "data": {"access": "full", "reason": None}}

    if lesson > 60:
        return {
            "success": True,
            "data": {"access": "blocked", "reason": "need_payment_or_code"},
        }

    return {"success": True, "data": {"access": "free", "reason": None}}


# ── 支付宝当面付（python-alipay-sdk）─────────────────────────

def _ensure_pem(key: str, marker: str) -> str:
    if key.startswith("-----"):
        return key
    return f"-----BEGIN {marker}-----\n{key}\n-----END {marker}-----"


def _get_alipay():
    from alipay import AliPay

    app_id = os.environ.get("ALIPAY_APP_ID", "")
    private_key = os.environ.get("ALIPAY_PRIVATE_KEY", "")
    alipay_public_key = os.environ.get("ALIPAY_PUBLIC_KEY", "")

    if not all([app_id, private_key, alipay_public_key]):
        return None

    return AliPay(
        appid=app_id,
        app_private_key_string=_ensure_pem(private_key, "PRIVATE KEY"),
        alipay_public_key_string=_ensure_pem(alipay_public_key, "PUBLIC KEY"),
        sign_type="RSA2",
    )


@router.post("/payment/create")
def create_payment(body: CreatePaymentBody, request: Request, db: Session = Depends(get_db)):
    sid = body.shibie_id.strip()
    if not sid:
        return {"success": False, "error": "shibie_id 不能为空"}

    user = db.execute(
        text("SELECT access_level FROM users WHERE shibie_id = :sid"), {"sid": sid}
    ).fetchone()
    if not user:
        return {"success": False, "error": "用户不存在"}

    if user._mapping["access_level"] in ("paid", "invited"):
        return {"success": False, "error": "已有完整权限"}

    alipay = _get_alipay()
    if not alipay:
        return {"success": False, "error": "支付功能暂未配置"}

    out_trade_no = "LS" + "".join(random.choices(string.digits, k=14)) + "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=4))

    host = request.headers.get("host", "lumis.tpr.wales")
    scheme = "https" if "tpr.wales" in host else "http"
    notify_url = f"{scheme}://{host}/api/payment/callback"

    try:
        result = alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=PAYMENT_AMOUNT,
            subject=PAYMENT_SUBJECT,
            timeout_express=PAYMENT_TIMEOUT,
            notify_url=notify_url,
        )
    except Exception as e:
        return {"success": False, "error": f"支付宝接口调用失败: {e}"}

    if result.get("code") != "10000":
        return {"success": False, "error": result.get("sub_msg") or result.get("msg") or "创建订单失败"}

    qr_code = result.get("qr_code", "")
    if not qr_code:
        return {"success": False, "error": "未获取到二维码"}

    qr_data_url = None
    try:
        import qrcode as qr_mod
        img = qr_mod.make(qr_code)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        pass

    db.execute(
        payments.insert().values(
            shibie_id=sid, out_trade_no=out_trade_no,
            amount=PAYMENT_AMOUNT, created_at=_now(),
        )
    )
    db.commit()

    return {
        "success": True,
        "data": {
            "order_id": out_trade_no,
            "qr_data_url": qr_data_url,
            "qr_code": qr_code,
        },
    }


@router.post("/payment/callback")
async def payment_callback(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    params = urllib.parse.parse_qs(body.decode("utf-8"))
    params = {k: v[0] for k, v in params.items()}

    alipay = _get_alipay()
    if not alipay:
        return "fail"

    sign = params.pop("sign", None)
    params.pop("sign_type", None)
    if not sign:
        return "fail"

    unsigned_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v)
    try:
        verified = alipay.verify(unsigned_str, sign)
    except Exception:
        verified = False

    if not verified:
        return "fail"

    trade_status = params.get("trade_status", "")
    out_trade_no = params.get("out_trade_no", "")

    if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        row = db.execute(
            text("SELECT * FROM payments WHERE out_trade_no = :no"), {"no": out_trade_no}
        ).fetchone()
        if row and row._mapping["status"] != "paid":
            sid = row._mapping["shibie_id"]
            db.execute(
                text("UPDATE payments SET status = 'paid', paid_at = :now WHERE out_trade_no = :no"),
                {"now": _now(), "no": out_trade_no},
            )
            db.execute(
                text("UPDATE users SET access_level = 'paid', paid_at = :now, updated_at = :now WHERE shibie_id = :sid"),
                {"now": _now(), "sid": sid},
            )

            # ── 收益分成：查找邀请人，给推广者分成 ──
            ref = db.execute(
                text("SELECT inviter_shibie_id, invite_code FROM referrals WHERE invitee_shibie_id = :sid"),
                {"sid": sid},
            ).fetchone()
            if ref:
                inviter_sid = ref._mapping["inviter_shibie_id"]
                now = _now()
                db.execute(
                    earnings.insert().values(
                        earner_shibie_id=inviter_sid,
                        source_shibie_id=sid,
                        payment_trade_no=out_trade_no,
                        amount=EARNING_AMOUNT,
                        status="credited",
                        created_at=now,
                    )
                )
                db.execute(
                    text("UPDATE users SET total_earnings = total_earnings + :amt, "
                         "available_balance = available_balance + :amt, "
                         "torch_points = torch_points + 20, "
                         "updated_at = :now WHERE shibie_id = :sid"),
                    {"amt": EARNING_AMOUNT, "now": now, "sid": inviter_sid},
                )
                db.execute(
                    torch_points_log.insert().values(
                        shibie_id=inviter_sid, points=20,
                        reason=f"邀请用户付费成功，获得 ¥{EARNING_AMOUNT}",
                        source_type="payment", source_id=out_trade_no,
                        created_at=now,
                    )
                )

            db.commit()

    return "success"


@router.get("/payment/status/{order_id}")
def payment_status(order_id: str, db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT status FROM payments WHERE out_trade_no = :no"), {"no": order_id}
    ).fetchone()
    if not row:
        return {"success": False, "error": "订单不存在"}

    paid = row._mapping["status"] == "paid"
    return {"success": True, "data": {"paid": paid, "status": row._mapping["status"]}}
