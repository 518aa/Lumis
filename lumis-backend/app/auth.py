"""JWT 认证 + 密码工具"""

import os
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Header, Request
from fastapi.responses import RedirectResponse
from typing import Optional

from sqlalchemy import text

from app.database import get_db

SECRET_KEY = os.environ.get("LUMIS_SECRET_KEY", "lumis-dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


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
