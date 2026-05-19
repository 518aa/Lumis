"""JWT 认证 + 密码工具"""

import os
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, Header, Request
from fastapi.responses import RedirectResponse
from typing import Optional

from sqlalchemy import text

from app.database import get_db

SECRET_KEY = os.environ.get("LUMIS_SECRET_KEY", "lumis-dev-DO-NOT-USE-IN-PROD-2024-xK9mP2vN8qR4wT6")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")) -> bool:
    """内部 API 鉴权：X-API-Key header 或 MCP 内部调用"""
    internal_key = os.environ.get("LUMIS_API_KEY", "")
    if not internal_key:
        return True
    if x_api_key == internal_key:
        return True
    raise HTTPException(status_code=403, detail="Invalid API key")


def create_access_token(account_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(account_id), "exp": expire, "type": "access"}, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(account_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(account_id), "exp": expire, "type": "refresh"}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_account_id(authorization: str = Header(..., alias="Authorization")) -> int:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization[7:]
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return int(payload["sub"])


def get_current_account(account_id: int = Depends(get_current_account_id), db=Depends(get_db)) -> dict:
    row = db.execute(text("SELECT * FROM accounts WHERE id = :id"), {"id": account_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return dict(row._mapping)


ADMIN_PASSWORD = os.environ.get("LUMIS_ADMIN_PASSWORD", "lumis-admin-2025")


def create_admin_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": "admin", "exp": expire, "type": "admin"}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_admin(request: Request):
    """Admin cookie 鉴权，未登录 302 跳转"""
    token = request.cookies.get("admin_token")
    if not token:
        return RedirectResponse(url="/admin/login", status_code=302)

    payload = decode_token(token)
    if not payload or payload.get("type") != "admin":
        resp = RedirectResponse(url="/admin/login", status_code=302)
        resp.delete_cookie("admin_token")
        return resp
    return True


def get_current_account_from_cookie(request: Request, db=Depends(get_db)) -> dict:
    """Cookie/URL token 鉴权，用于 Dashboard 页面"""
    token = request.cookies.get("access_token") or request.query_params.get("token")
    if not token:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        resp = RedirectResponse(url="/dashboard/login", status_code=302)
        resp.delete_cookie("access_token")
        return resp

    account_id = int(payload["sub"])
    row = db.execute(text("SELECT * FROM accounts WHERE id = :id"), {"id": account_id}).fetchone()
    if not row:
        resp = RedirectResponse(url="/dashboard/login", status_code=302)
        resp.delete_cookie("access_token")
        return resp

    account = dict(row._mapping)

    # 查找绑定的 shibie_id
    device = db.execute(
        text("SELECT shibie_id FROM devices WHERE account_id = :aid AND is_active = 1 ORDER BY id DESC LIMIT 1"),
        {"aid": account["id"]},
    ).fetchone()
    account["shibie_id"] = device._mapping["shibie_id"] if device else ""

    return account
