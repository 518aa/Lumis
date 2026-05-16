"""认证 API — 注册 / 登录 / 刷新 Token"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_account, get_current_account_id,
)
import sqlite3

router = APIRouter()


class RegisterBody(BaseModel):
    email: str
    password: str
    username: str = ""
    shibie_id: str = ""


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

    existing = db.execute("SELECT id FROM accounts WHERE email = ?", (body.email,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="邮箱已注册")

    # 创建 account
    cursor = db.execute(
        "INSERT INTO accounts (email, password_hash, username) VALUES (?, ?, ?)",
        (body.email, hash_password(body.password), body.username or body.email.split("@")[0]),
    )
    account_id = cursor.lastrowid

    # 创建关联的 user（学习数据）
    import uuid
    shibie_id = body.shibie_id or str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (shibie_id, name) VALUES (?, ?)",
        (shibie_id, body.username or body.email.split("@")[0]),
    )

    # 绑定设备
    db.execute(
        "INSERT INTO devices (account_id, shibie_id) VALUES (?, ?)",
        (account_id, shibie_id),
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
    row = db.execute("SELECT * FROM accounts WHERE email = ?", (body.email,)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    account_id = row["id"]

    # 获取绑定的 shibie_id
    device = db.execute(
        "SELECT shibie_id FROM devices WHERE account_id = ? AND is_active = 1 LIMIT 1",
        (account_id,),
    ).fetchone()
    shibie_id = device["shibie_id"] if device else None

    return {
        "success": True,
        "data": {
            "account_id": account_id,
            "shibie_id": shibie_id,
            "username": row["username"],
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
        "SELECT shibie_id FROM devices WHERE account_id = ? AND is_active = 1 LIMIT 1",
        (account_id,),
    ).fetchone()

    user_data = None
    if device:
        user_row = db.execute("SELECT * FROM users WHERE shibie_id = ?", (device["shibie_id"],)).fetchone()
        if user_row:
            import json
            user_data = dict(user_row)
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
    params = []
    if body.username:
        updates.append("username = ?")
        params.append(body.username)
        # 同步更新 users.name
        device = db.execute(
            "SELECT shibie_id FROM devices WHERE account_id = ? AND is_active = 1 LIMIT 1",
            (account_id,),
        ).fetchone()
        if device:
            db.execute("UPDATE users SET name = ? WHERE shibie_id = ?", (body.username, device["shibie_id"]))
    if body.avatar:
        updates.append("avatar = ?")
        params.append(body.avatar)

    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(account_id)
        db.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()

    return {"success": True, "data": {"username": body.username or account["username"], "avatar": body.avatar or account["avatar"]}}
