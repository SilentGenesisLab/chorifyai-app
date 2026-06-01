"""File upload → Aliyun OSS. Accepts image / audio / video / generic file."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.services.oss import delete_objects, put_object

router = APIRouter(prefix="/api/upload", tags=["upload"])

KIND_EXT: dict[str, set[str] | None] = {
    "image": {".jpg", ".jpeg", ".png", ".webp"},
    "audio": {".mp3", ".wav", ".m4a", ".aac"},
    "video": {".mp4", ".mov", ".webm"},
    "file": None,  # any extension
}


@router.post("")
async def upload(file: UploadFile = File(...), kind: str = Form("file")):
    if kind not in KIND_EXT:
        raise HTTPException(status_code=400, detail=f"非法的 kind: {kind}")

    ext = os.path.splitext(file.filename or "")[1].lower()
    allowed = KIND_EXT[kind]
    if allowed is not None and ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的{kind}格式 {ext or '(无扩展名)'}",
        )

    data = await file.read()
    size_mb = len(data) / 1024 / 1024
    if size_mb > settings.max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大 {size_mb:.1f}MB（上限 {settings.max_upload_mb}MB）",
        )

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"uploads/{kind}/{day}/{uuid.uuid4().hex}{ext}"
    url = put_object(key, data, file.content_type)

    return {
        "ok": True,
        "url": url,
        "key": key,
        "kind": kind,
        "name": file.filename,
        "size": len(data),
        "contentType": file.content_type,
    }


class DeleteBody(BaseModel):
    keys: list[str]


@router.post("/delete")
async def delete(body: DeleteBody) -> dict:
    """Remove objects from OSS (called server-side by the Next drive API when a
    file is permanently deleted). Best-effort — never raises on missing keys."""
    deleted = delete_objects(body.keys)
    return {"ok": True, "deleted": deleted}
