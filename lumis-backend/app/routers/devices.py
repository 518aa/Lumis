"""设备绑定 API"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
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
        "SELECT account_id FROM devices WHERE shibie_id = ? AND is_active = 1",
        (shibie_id,),
    ).fetchone()
    if existing:
        if existing["account_id"] != account_id:
            raise HTTPException(status_code=409, detail="设备已绑定其他账号")
        return {"success": True, "data": {"shibie_id": shibie_id, "message": "已绑定"}}

    # 确保对应的 user 记录存在
    user = db.execute("SELECT 1 FROM users WHERE shibie_id = ?", (shibie_id,)).fetchone()
    if not user:
        import json
        db.execute(
            "INSERT INTO users (shibie_id, name) VALUES (?, ?)",
            (shibie_id, ""),
        )

    # 停用旧设备
    db.execute("UPDATE devices SET is_active = 0 WHERE account_id = ?", (account_id,))

    # 绑定新设备
    db.execute(
        "INSERT INTO devices (account_id, shibie_id, device_name) VALUES (?, ?, ?)",
        (account_id, shibie_id, body.device_name),
    )
    db.commit()

    return {"success": True, "data": {"shibie_id": shibie_id}}


@router.post("/device/unbind")
def unbind_device(body: BindDeviceBody, account_id: int = Depends(get_current_account_id), db=Depends(get_db)):
    if not body.shibie_id:
        raise HTTPException(status_code=400, detail="需要 shibie_id")

    db.execute(
        "UPDATE devices SET is_active = 0 WHERE account_id = ? AND shibie_id = ?",
        (account_id, body.shibie_id),
    )
    db.commit()
    return {"success": True, "data": {"shibie_id": body.shibie_id, "message": "已解绑"}}
