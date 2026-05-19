"""认证 API — 注册 / 登录 / 刷新 Token"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text

from app.database import get_db, _now
from app.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_account, get_current_account_id,
)

router = APIRouter()


class RegisterBody(BaseModel):
    email: str
    password: str
    username: str = ""
    shibie_id: str = ""
    invite_code: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


class UpdateProfileBody(BaseModel):
    username: str = ""
    avatar: str = ""


@router.post("/auth/register")
def register(body: RegisterBody, db=Depends(get_db)):
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6位")

    existing = db.execute(
        text("SELECT id FROM accounts WHERE email = :email"), {"email": body.email}
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="邮箱已注册")

    username = body.username or body.email.split("@")[0]
    result = db.execute(
        text("INSERT INTO accounts (email, password_hash, username, created_at, updated_at) VALUES (:email, :ph, :username, :now, :now)"),
        {"email": body.email, "ph": hash_password(body.password), "username": username, "now": _now()},
    )

    # 获取新插入的 account_id
    account_id = result.lastrowid
    # lastrowid 在 PostgreSQL 下可能不可靠，用 RETURNING 更安全
    if account_id is None:
        row = db.execute(text("SELECT lastval()")).fetchone()
        account_id = row[0]

    # 创建关联的 user（学习数据），shibie_id 冲突时自动生成新的
    shibie_id = body.shibie_id or str(uuid.uuid4())
    existing_user = db.execute(
        text("SELECT shibie_id FROM users WHERE shibie_id = :sid"), {"sid": shibie_id}
    ).fetchone()
    if existing_user:
        shibie_id = str(uuid.uuid4())

    access_level = "free"
    inviter_sid = None
    ic = body.invite_code.strip().upper() if body.invite_code else ""

    if ic:
        from app.routers.payment import CODE_CHARS
        if all(c in CODE_CHARS for c in ic) and len(ic) == 4:
            code_row = db.execute(
                text("SELECT * FROM invite_codes WHERE code = :c"), {"c": ic}
            ).fetchone()
            if not code_row:
                raise HTTPException(status_code=400, detail="邀请码不存在，请联系官方获取")
            if code_row._mapping["owner_shibie_id"] == shibie_id:
                raise HTTPException(status_code=400, detail="不能使用自己的邀请码")
            access_level = "invited"
            inviter_sid = code_row._mapping["owner_shibie_id"]
            db.execute(
                text("UPDATE invite_codes SET used_count = used_count + 1 WHERE code = :c"),
                {"c": ic},
            )
        else:
            raise HTTPException(status_code=400, detail="邀请码格式不正确，请联系官方获取")

    db.execute(
        text("INSERT INTO users (shibie_id, name, access_level, invite_code, created_at, updated_at) VALUES (:sid, :name, :level, '', :now, :now)"),
        {"sid": shibie_id, "name": username, "level": access_level, "now": _now()},
    )

    if inviter_sid:
        from app.database import referrals
        db.execute(
            referrals.insert().values(
                invite_code=ic, inviter_shibie_id=inviter_sid,
                invitee_shibie_id=shibie_id, created_at=_now(),
            )
        )

    # 绑定设备
    db.execute(
        text("INSERT INTO devices (account_id, shibie_id, created_at) VALUES (:aid, :sid, :now)"),
        {"aid": account_id, "sid": shibie_id, "now": _now()},
    )
    db.commit()

    return {
        "success": True,
        "data": {
            "account_id": account_id,
            "shibie_id": shibie_id,
            "access_token": create_access_token(account_id),
            "refresh_token": create_refresh_token(account_id),
        },
    }


@router.post("/auth/login")
def login(body: LoginBody, db=Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM accounts WHERE email = :email"), {"email": body.email}
    ).fetchone()
    if not row or not verify_password(body.password, row._mapping["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    account_id = row._mapping["id"]

    # 获取绑定的 shibie_id
    device = db.execute(
        text("SELECT shibie_id FROM devices WHERE account_id = :aid AND is_active = 1 LIMIT 1"),
        {"aid": account_id},
    ).fetchone()
    shibie_id = device._mapping["shibie_id"] if device else None

    return {
        "success": True,
        "data": {
            "account_id": account_id,
            "shibie_id": shibie_id,
            "username": row._mapping["username"],
            "access_token": create_access_token(account_id),
            "refresh_token": create_refresh_token(account_id),
        },
    }


@router.post("/auth/refresh")
def refresh_token(body: RefreshBody):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    account_id = int(payload["sub"])
    return {
        "success": True,
        "data": {
            "access_token": create_access_token(account_id),
            "refresh_token": create_refresh_token(account_id),
        },
    }


@router.get("/profile")
def get_profile(account=Depends(get_current_account), db=Depends(get_db)):
    account_id = account["id"]

    device = db.execute(
        text("SELECT shibie_id FROM devices WHERE account_id = :aid AND is_active = 1 LIMIT 1"),
        {"aid": account_id},
    ).fetchone()

    user_data = None
    if device:
        user_row = db.execute(
            text("SELECT * FROM users WHERE shibie_id = :sid"),
            {"sid": device._mapping["shibie_id"]},
        ).fetchone()
        if user_row:
            import json
            user_data = dict(user_row._mapping)
            user_data["completed_lessons"] = json.loads(user_data["completed_lessons"])

    return {
        "success": True,
        "data": {
            "account_id": account_id,
            "email": account["email"],
            "username": account["username"],
            "avatar": account["avatar"],
            "user": user_data,
        },
    }


@router.put("/profile")
def update_profile(body: UpdateProfileBody, account=Depends(get_current_account), db=Depends(get_db)):
    account_id = account["id"]
    updates = []
    params: dict = {"aid": account_id, "now": _now()}
    if body.username:
        updates.append("username = :username")
        params["username"] = body.username
        # 同步更新 users.name
        device = db.execute(
            text("SELECT shibie_id FROM devices WHERE account_id = :aid AND is_active = 1 LIMIT 1"),
            {"aid": account_id},
        ).fetchone()
        if device:
            db.execute(
                text("UPDATE users SET name = :name, updated_at = :now WHERE shibie_id = :sid"),
                {"name": body.username, "now": _now(), "sid": device._mapping["shibie_id"]},
            )
    if body.avatar:
        updates.append("avatar = :avatar")
        params["avatar"] = body.avatar

    if updates:
        updates.append("updated_at = :now")
        db.execute(
            text(f"UPDATE accounts SET {', '.join(updates)} WHERE id = :aid"),
            params,
        )
        db.commit()

    return {"success": True, "data": {"username": body.username or account["username"], "avatar": body.avatar or account["avatar"]}}
