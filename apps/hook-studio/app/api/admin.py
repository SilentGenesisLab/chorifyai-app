from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.models import Role
from app.quota import china_day, next_reset_at

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin(request: Request) -> Any:
    principal = getattr(request.state, "session", None) or getattr(request.state, "principal", None)
    principal = getattr(principal, "principal", principal)
    role = principal.get("role") if isinstance(principal, dict) else getattr(principal, "role", None)
    if principal is None:
        raise HTTPException(status_code=401, detail={"error_code": "AUTH_REQUIRED", "message": "请先登录"})
    if str(getattr(role, "value", role)) != Role.ADMIN.value:
        raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN", "message": "仅管理员可操作"})
    return principal


class CodePatch(BaseModel):
    enabled: bool | None = None
    daily_video_limit: int | None = Field(default=None, ge=0, le=100)
    daily_image_limit: int | None = Field(default=None, ge=0, le=1000)


class SettingsPatch(BaseModel):
    global_video_daily_limit: int | None = Field(default=None, ge=1, le=1000)
    global_image_daily_limit: int | None = Field(default=None, ge=1, le=100000)
    image_concurrency: int | None = Field(default=None, ge=1, le=20)
    video_concurrency: int | None = Field(default=None, ge=1, le=20)


def _write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    _admin(request)
    db = request.app.state.db
    code_data = yaml.safe_load(Path(request.app.state.settings.access_codes_file).read_text(encoding="utf-8")) or {}
    day = china_day()
    with db.transaction() as conn:
        usage = [dict(row) for row in conn.execute("SELECT * FROM daily_usage ORDER BY day_cn DESC, client_id").fetchall()]
        settings = {row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT key,value FROM settings").fetchall()}
        status = {row["status"]: row["n"] for row in conn.execute("SELECT status,COUNT(*) n FROM jobs GROUP BY status").fetchall()}
        today = {row["client_id"]: dict(row) for row in conn.execute("SELECT * FROM daily_usage WHERE day_cn=?", (day,)).fetchall()}
        downloads = {row["client_id"]: row["n"] for row in conn.execute("SELECT client_id,COUNT(*) n FROM events WHERE action='download' GROUP BY client_id").fetchall()}
        ledger = [dict(row) for row in conn.execute(
            """SELECT client_id,resource,SUM(units) units FROM quota_ledger
            WHERE day_cn=? AND state IN ('reserved','committed') GROUP BY client_id,resource""", (day,),
        ).fetchall()]
        table_counts = {
            name: conn.execute(f"SELECT COUNT(*) n FROM {name}").fetchone()["n"]
            for name in ("conversations", "messages", "assets", "task_runs", "storyboards", "training_examples")
        }
    ledger_by_client = {(row["client_id"], row["resource"]): int(row["units"] or 0) for row in ledger}
    clients = []
    for item in code_data.get("codes", []):
        if item.get("role", "client") != "client":
            continue
        row = today.get(item.get("id"), {})
        clients.append({
            "id": item.get("id"), "name": item.get("client_name"), "enabled": item.get("enabled", True),
            "video_used": ledger_by_client.get((item.get("id"), "video"), int(row.get("video_reserved", 0)) + int(row.get("video_succeeded", 0))),
            "video_limit": item.get("daily_video_limit", 100),
            "image_used": ledger_by_client.get((item.get("id"), "image"), 0),
            "image_limit": item.get("daily_image_limit", 1000),
            "downloads": downloads.get(item.get("id"), 0),
        })
    global_used = sum(row["units"] for row in ledger if row["resource"] == "video")
    backup = getattr(request.app.state, "backup_status", None)
    return {
        "clients": clients,
        "usage": {"global_video_used": global_used, "global_video_limit": request.app.state.quota.global_limit, "reset_at": next_reset_at().isoformat()},
        "usage_rows": usage, "settings": settings, "jobs": status,
        "health": {"database": "ok", "backup": backup or "unknown"}, "tables": table_counts,
    }


@router.patch("/access-codes/{code_id}")
async def patch_access_code(code_id: str, patch: CodePatch, request: Request) -> dict[str, Any]:
    _admin(request)
    path = Path(request.app.state.settings.access_codes_file)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    record = next((item for item in data.get("codes", []) if item.get("id") == code_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "访问码不存在"})
    changes = patch.model_dump(exclude_none=True)
    if record.get("role", "client") == "admin" and changes.get("enabled") is False:
        admins = [item for item in data.get("codes", []) if item.get("role") == "admin" and item.get("enabled", True)]
        if len(admins) <= 1:
            raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "不能停用最后一个管理码"})
    record.update(changes)
    _write_yaml_atomic(path, data)
    return {"id": code_id, **changes}


@router.patch("/settings")
async def patch_settings(patch: SettingsPatch, request: Request) -> dict[str, Any]:
    _admin(request)
    values = patch.model_dump(exclude_none=True)
    if not values:
        return {"updated": {}}
    with request.app.state.db.transaction(immediate=True) as conn:
        for key, value in values.items():
            conn.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, json.dumps(value), datetime.now(timezone.utc).isoformat()))
    if "global_video_daily_limit" in values:
        request.app.state.quota.global_limit = int(values["global_video_daily_limit"])
        request.app.state.production.global_video_limit = int(values["global_video_daily_limit"])
    if "global_image_daily_limit" in values:
        request.app.state.production.global_image_limit = int(values["global_image_daily_limit"])
    return {"updated": values, "restart_required": any(key.endswith("concurrency") for key in values)}


@router.post("/backups")
async def create_backup(request: Request) -> dict[str, Any]:
    _admin(request)
    manager = request.app.state.backup
    archive = manager.create()
    manifest = manager.verify(archive)
    try:
        url = await manager.upload(archive)
    except Exception as exc:
        request.app.state.backup_status = f"本地备份已验证，OSS上传失败：{type(exc).__name__}"
        raise HTTPException(status_code=502, detail={"error_code": "BACKUP_UPLOAD_FAILED", "message": request.app.state.backup_status}) from exc
    status_value = {"created_at": manifest.created_at, "archive": archive.name, "oss_url": url, "verified": True}
    request.app.state.backup_status = status_value
    with request.app.state.db.transaction(immediate=True) as conn:
        conn.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES('last_backup',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (json.dumps(status_value, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
    return status_value


@router.post("/backups/verify")
async def verify_latest_backup(request: Request) -> dict[str, Any]:
    _admin(request)
    archives = sorted((request.app.state.settings.data_dir / "backups").glob("hook-studio-*.tar.gz"), reverse=True)
    if not archives:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "尚无本地备份"})
    manifest = request.app.state.backup.verify(archives[0])
    return {"archive": archives[0].name, "verified": True, "manifest": asdict(manifest)}


@router.get("/events/export")
async def export_events(request: Request) -> FileResponse:
    _admin(request)
    path = request.app.state.settings.events_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return FileResponse(path, media_type="application/x-ndjson", filename="hook-studio-events.jsonl")


@router.get("/training/export")
async def export_training(request: Request) -> FileResponse:
    _admin(request)
    directory = request.app.state.settings.data_dir / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"training-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    with request.app.state.db.transaction() as conn, path.open("w", encoding="utf-8") as output:
        rows = conn.execute("SELECT * FROM training_examples ORDER BY created_at,id").fetchall()
        for row in rows:
            item = dict(row)
            for key in ("input_json", "output_json", "labels_json", "quality_json"):
                item[key.removesuffix("_json")] = json.loads(item.pop(key) or "{}")
            output.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    return FileResponse(path, media_type="application/x-ndjson", filename="hook-studio-training.jsonl")


@router.get("/data/tables")
async def data_tables(request: Request, table: str = "conversations", limit: int = 200) -> dict[str, Any]:
    _admin(request)
    allowed = {"conversations", "messages", "assets", "asset_extractions", "task_runs", "storyboards", "storyboard_shots", "activity_events", "training_examples", "quota_ledger"}
    if table not in allowed:
        raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "不支持的数据表"})
    limit = max(1, min(1000, limit))
    with request.app.state.db.transaction() as conn:
        columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()]
    return {"table": table, "columns": columns, "rows": rows, "limit": limit}


@router.post("/insights")
async def create_insights(request: Request) -> dict[str, str]:
    _admin(request)
    directory = request.app.state.settings.data_dir / "insights"
    insight = request.app.state.insights.write_hook_insights(directory)
    digest = directory / "WEEKLY_DEMO_DIGEST.md"
    digest.write_text(request.app.state.insights.render_digest(), encoding="utf-8")
    return {"insights": insight.name, "digest": digest.name}
