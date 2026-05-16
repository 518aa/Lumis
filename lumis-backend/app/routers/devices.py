"""设备绑定 API"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.database import get_db, _now
from app.auth import get_current_account_id

router = APIRouter()


class BindDeviceBody(BaseModel):
    shibie_id: str = ""
    device_name: str = ""


@router.post("/device/bind")
def bind_device(body: BindDeviceBody, account_id: int = Depends(get_current_account_id), db=Depends(get_db)):
    shibie_id = body.shibie_id or str(uuid.uuid4())

    # 检查设备是否已绑定其他账号
    existing = db.execute(
        text("SELECT account_id FROM devices WHERE shibie_id = :sid AND is_active = 1"),
        {"sid": shibie_id},
    ).fetchone()
    if existing:
        if existing._mapping["account_id"] != account_id:
            raise HTTPException(status_code=409, detail="设备已绑定其他账号")
        return {"success": True, "data": {"shibie_id": shibie_id, "message": "已绑定"}}

    # 确保对应的 user 记录存在
    user = db.execute(
        text("SELECT 1 FROM users WHERE shibie_id = :sid"), {"sid": shibie_id}
    ).fetchone()
    if not user:
        db.execute(
            text("INSERT INTO users (shibie_id, name, created_at, updated_at) VALUES (:sid, :name, :now, :now)"),
            {"sid": shibie_id, "name": "", "now": _now()},
        )

    # 停用旧设备
    db.execute(
        text("UPDATE devices SET is_active = 0 WHERE account_id = :aid"),
        {"aid": account_id},
    )

    # 绑定新设备
    db.execute(
        text("INSERT INTO devices (account_id, shibie_id, device_name, created_at) VALUES (:aid, :sid, :dname, :now)"),
        {"aid": account_id, "sid": shibie_id, "dname": body.device_name, "now": _now()},
    )
    db.commit()

    return {"success": True, "data": {"shibie_id": shibie_id}}


@router.post("/device/unbind")
def unbind_device(body: BindDeviceBody, account_id: int = Depends(get_current_account_id), db=Depends(get_db)):
    if not body.shibie_id:
        raise HTTPException(status_code=400, detail="需要 shibie_id")

    db.execute(
        text("UPDATE devices SET is_active = 0 WHERE account_id = :aid AND shibie_id = :sid"),
        {"aid": account_id, "sid": body.shibie_id},
    )
    db.commit()
    return {"success": True, "data": {"shibie_id": body.shibie_id, "message": "已解绑"}}
