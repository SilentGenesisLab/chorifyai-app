from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.services.local_storage import safe_path_for_key, set_storage_root, storage_root

router = APIRouter(prefix="/api/local-storage", tags=["local-storage"])
files_router = APIRouter(prefix="/api/local-files", tags=["local-files"])


class LocalStorageBody(BaseModel):
    root: str


@router.get("")
def get_local_storage() -> dict:
    root = storage_root()
    return {
        "ok": True,
        "provider": settings.oss_provider,
        "root": str(root),
        "enabled": settings.oss_provider == "local",
    }


@router.post("")
def update_local_storage(body: LocalStorageBody) -> dict:
    if not body.root.strip():
        raise HTTPException(status_code=400, detail="本地路径不能为空")
    try:
        root = set_storage_root(body.root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法使用该本地路径: {exc}") from exc
    return {"ok": True, "provider": settings.oss_provider, "root": str(root), "enabled": settings.oss_provider == "local"}


@files_router.get("/{key:path}", include_in_schema=False)
def get_local_file(key: str):
    try:
        path = safe_path_for_key(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="本地文件不存在")
    return FileResponse(path)
