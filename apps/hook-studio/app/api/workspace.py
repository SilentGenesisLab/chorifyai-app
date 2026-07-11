from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.quota import next_reset_at
from app.models import EventAction, EventRecord, Mode
from app.repositories.workspace import (
    QuotaExceeded,
    WorkspaceConflict,
    WorkspaceNotFound,
    WorkspaceRepository,
)
from app.services.ingestion import AttachmentIngestionService, IngestedContent, IngestionError
from app.url_policy import is_sendable_media_url


router = APIRouter(prefix="/api/studio", tags=["workspace"])

TOOL_MAP = {
    "create_video": ("create", "视频生产"),
    "create_image": ("image", "图片生成"),
    "reference_remix": ("replicate", "参控复刻"),
    "batch_production": ("batch", "批量生产"),
    "reverse_analysis": ("reverse", "逆向分析"),
    "replace_content": ("replace", "定向替换"),
}
TOOL_REVERSE = {value[0]: key for key, value in TOOL_MAP.items()}
STAGE_MAP = {
    "queued": "解析素材",
    "analyzing": "解析素材",
    "reverse_analysis": "逆向分析",
    "planning": "分镜规划",
    "storyboard_review": "等待确认",
    "revision_requested": "分镜规划",
    "confirmed": "镜头生成",
    "generating": "镜头生成",
    "assembling": "后期合成",
    "completed": "技术质检",
    "failed": "技术质检",
}
PUBLIC_INTERNAL_FIELDS = {
    "apikey", "endpoint", "model", "modelid", "modelname", "private",
    "privatetrace", "prompt", "promptfinal", "provider", "providerid",
    "providername", "providertrace", "raw", "secret", "token", "trace",
}


def _principal(request: Request) -> Any:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail={"error_code": "AUTH_REQUIRED", "message": "请先登录"})
    return principal


def _repo(request: Request) -> WorkspaceRepository:
    return request.app.state.workspace


def _value(principal: Any, name: str, default: Any = None) -> Any:
    return principal.get(name, default) if isinstance(principal, dict) else getattr(principal, name, default)


def _public_projection(value: Any) -> Any:
    if isinstance(value, list):
        return [_public_projection(item) for item in value]
    if not isinstance(value, dict):
        return value
    projected: dict[str, Any] = {}
    for key, item in value.items():
        normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if normalized in PUBLIC_INTERNAL_FIELDS or "provider" in normalized or normalized.startswith("model"):
            continue
        if isinstance(item, str) and (normalized.endswith("url") or normalized.endswith("uri")):
            projected[key] = item.strip() if is_sendable_media_url(item) else ""
            continue
        if isinstance(item, list) and normalized.endswith("urls"):
            projected[key] = [url.strip() for url in item if is_sendable_media_url(url)]
            continue
        projected[key] = _public_projection(item)
    return projected


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (WorkspaceNotFound,)):
        return HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "资源不存在"})
    if isinstance(exc, (WorkspaceConflict,)):
        return HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": str(exc)})
    if isinstance(exc, QuotaExceeded):
        return HTTPException(status_code=429, detail={"error_code": "QUOTA_EXHAUSTED", "message": "今日额度不足", "usage": exc.snapshot})
    if isinstance(exc, IngestionError):
        return HTTPException(status_code=422, detail={"error_code": "ATTACHMENT_INVALID", "message": str(exc)})
    return HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": str(exc)})


def _sendable_asset_url(asset: dict[str, Any] | None) -> str:
    if not asset or asset.get("status") != "ready":
        return ""
    for candidate in (asset.get("storage_uri"), asset.get("source_url")):
        if is_sendable_media_url(candidate):
            return str(candidate).strip()
    return ""


def _asset_payload(asset: dict[str, Any]) -> dict[str, Any]:
    metadata = asset.get("metadata") or {}
    url = _sendable_asset_url(asset)
    thumbnail = metadata.get("thumbnail_url")
    thumbnail_url = str(thumbnail).strip() if is_sendable_media_url(thumbnail) else ""
    return {
        "id": asset["id"],
        "type": asset.get("media_type") or "document",
        "name": asset.get("filename") or ("生成视频" if asset.get("media_type") == "video" else "生成图片"),
        "url": url,
        "thumbnail_url": thumbnail_url or (url if asset.get("media_type") == "image" else ""),
        "duration_seconds": metadata.get("duration_seconds") or metadata.get("duration"),
        "width": metadata.get("width"),
        "height": metadata.get("height"),
        "job_id": metadata.get("job_id"),
        "created_at": asset.get("created_at"),
    }


def _bound_assets(repo: WorkspaceRepository, message_id: str) -> list[tuple[dict[str, Any], str]]:
    with repo.db.transaction() as conn:
        rows = conn.execute(
            """SELECT a.*,ma.usage,ma.ordinal,x.text_content FROM message_assets ma
            JOIN assets a ON a.id=ma.asset_id
            LEFT JOIN asset_extractions x ON x.asset_id=a.id AND x.status='succeeded'
            WHERE ma.message_id=? ORDER BY ma.usage,ma.ordinal""",
            (message_id,),
        ).fetchall()
    return [(dict(row), str(row["usage"])) for row in rows]


def _storyboard_payload(repo: WorkspaceRepository, board: dict[str, Any], estimated: int | None = None) -> dict[str, Any]:
    if board.get("id"):
        with repo.db.transaction() as conn:
            owner = conn.execute(
                """SELECT t.client_id FROM storyboards s JOIN task_runs t ON t.id=s.task_id
                WHERE s.id=?""", (board["id"],),
            ).fetchone()
        if owner:
            full = repo.get_storyboard(board["id"], client_id=owner["client_id"])
            if full:
                board = full
    shots = []
    for shot in board.get("shots") or []:
        image_asset = repo.get_asset(str(shot.get("image_asset_id"))) if shot.get("image_asset_id") else None
        payload = shot.get("payload") or {}
        panels = []
        for panel in shot.get("panels") or []:
            selected = repo.get_asset(str(panel.get("selected_asset_id"))) if panel.get("selected_asset_id") else None
            annotated = repo.get_asset(str(panel.get("annotated_asset_id"))) if panel.get("annotated_asset_id") else None
            approved = bool(panel.get("approved"))
            public_role = "end" if panel.get("role") == "result" else panel.get("role")
            panels.append({
                "id": panel["id"], "logical_key": panel.get("logical_key"),
                "order": panel.get("ordinal"), "revision": panel.get("revision", 1),
                "role": public_role, "required": bool(panel.get("required")),
                "description": panel.get("description") or "", "annotation": panel.get("annotation") or {},
                "clean_asset_id": panel.get("clean_asset_id"), "selected_asset_id": panel.get("selected_asset_id"),
                "clean_url": _sendable_asset_url(selected),
                "annotated_url": _sendable_asset_url(annotated),
                "send_to_provider": bool(panel.get("send_to_provider")),
                "approved": approved, "status": "approved" if approved else panel.get("status") or "draft",
                "approval": {"scope": "panel", "scope_id": panel["id"], "decision": "approved",
                             "version": panel.get("revision", 1)} if approved else None,
            })
        contract = {key: payload.get(key) for key in (
            "story_function", "visual", "shot_size", "camera_angle", "camera_height", "lens_feel",
            "composition", "action_start", "action_trigger", "action_result", "camera_move", "sound",
            "transition", "stable_truth", "may_vary", "reference_manifest", "first_failure_cue",
        )}
        shots.append({
            "id": shot["id"], "order": shot.get("ordinal"), "title": shot.get("title") or f"镜头 {shot.get('ordinal')}",
            "description": shot.get("description") or "", "duration_seconds": shot.get("duration_seconds") or 0,
            "image_url": _sendable_asset_url(image_asset) or (
                str(payload.get("image_url")).strip() if is_sendable_media_url(payload.get("image_url")) else ""
            ),
            "revision": shot.get("revision", 1), "approved": bool(shot.get("approved")),
            "status": "approved" if shot.get("approved") else "draft", "panels": panels,
            **contract, "action_end": contract.get("action_result"), "lens": contract.get("lens_feel"),
            "audio": contract.get("sound"),
            "selected_clean_frame_url": next((panel["clean_url"] for panel in panels if panel["send_to_provider"]), ""),
            "approval": {"scope": "shot", "scope_id": shot["id"], "decision": "approved",
                         "version": shot.get("revision", 1)} if shot.get("approved") else None,
            "contract": contract,
        })
    total = sum(float(item["duration_seconds"] or 0) for item in shots)
    raw_status = board.get("status")
    public_status = "confirmed" if raw_status == "confirmed" else "revision_required" if raw_status == "revision_required" else "pending"
    animatic_asset = repo.get_asset(str(board.get("animatic_asset_id"))) if board.get("animatic_asset_id") else None
    coverage = board.get("coverage") or {
        "shots_total": len(shots), "shots_approved": sum(1 for shot in shots if shot["approved"]),
        "panels_total": sum(len(shot["panels"]) for shot in shots),
        "panels_approved": sum(1 for shot in shots for panel in shot["panels"] if panel["approved"]),
        "clean_frames": sum(1 for shot in shots if any(panel.get("selected_asset_id") for panel in shot["panels"])),
    }
    skill_runs = [{
        "id": item["id"], "skill_id": item.get("skill_id"), "version": item.get("skill_version"),
        "stage": item.get("stage"), "status": "succeeded" if item.get("status") == "passed" else item.get("status"), "blocking": bool(item.get("blocking")),
        "label": item.get("public_label"), "duration_ms": item.get("duration_ms"), "latency_ms": item.get("duration_ms"),
        "input_count": item.get("input_count"), "output_count": item.get("output_count"),
        "retry_count": item.get("retry_count"), "blocking_reason": item.get("blocking_reason"),
    } for item in board.get("skill_runs") or []]
    can_produce = bool(
        shots and coverage.get("shots_approved") == coverage.get("shots_total")
        and coverage.get("panels_approved") == coverage.get("panels_total")
        and coverage.get("clean_frames") == coverage.get("shots_total")
        and board.get("board_approved") and board.get("animatic_status") == "confirmed"
    )
    blockers = []
    if coverage.get("shots_approved") != coverage.get("shots_total"): blockers.append("仍有镜头等待批准")
    if coverage.get("panels_approved") != coverage.get("panels_total"): blockers.append("仍有必需Panel等待批准")
    if coverage.get("clean_frames") != coverage.get("shots_total"): blockers.append("clean frame尚未覆盖全部镜头")
    if not board.get("board_approved"): blockers.append("整板尚未批准")
    if board.get("animatic_status") != "confirmed": blockers.append("动态预演尚未确认")
    public_coverage = {
        **coverage,
        "shot_total": coverage.get("shots_total", len(shots)),
        "shot_ready": len(shots),
        "panel_required": coverage.get("panels_total", 0),
        "panel_ready": coverage.get("panels_total", 0),
        "clean_ready": coverage.get("clean_frames", 0),
        "approved_shots": coverage.get("shots_approved", 0),
    }
    return _public_projection({
        "id": board["id"], "version": f"v{board.get('version', 1)}",
        "task_id": board.get("task_id"),
        "revision": int(board.get("revision") or 1),
        "status": public_status,
        "summary": board.get("summary") or "", "total_duration_seconds": total,
        "estimated_video_units": estimated or len(shots), "shots": shots,
        "coverage": public_coverage, "board_approved": bool(board.get("board_approved")),
        "animatic": {"id": board.get("animatic_asset_id") or f"animatic-{board['id']}",
                     "status": board.get("animatic_status") or "missing",
                     "asset_id": board.get("animatic_asset_id"),
                     "url": _sendable_asset_url(animatic_asset), "duration_seconds": total,
                     "version": int(board.get("revision") or 1),
                     "confirmed": board.get("animatic_status") == "confirmed"},
        "skill_runs": skill_runs, "can_produce": can_produce,
        "guard": {"can_produce": can_produce, "blockers": blockers},
        "frozen": bool(board.get("frozen_snapshot_hash")),
        "updated_at": board.get("updated_at") or board.get("created_at"),
    })


def _message_payload(repo: WorkspaceRepository, message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content") or {}
    attachments: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    for raw, usage in _bound_assets(repo, message["id"]):
        asset = dict(raw)
        asset["metadata"] = json.loads(asset.pop("metadata_json", "{}") or "{}")
        if usage in {"input", "reference"}:
            url = _sendable_asset_url(asset)
            attachments.append({
                "id": asset["id"], "name": asset.get("filename") or "附件", "kind": asset.get("media_type") or "file",
                "mime_type": asset.get("mime_type"), "size": asset.get("byte_size"),
                "url": url,
                "thumbnail_url": url if asset.get("media_type") == "image" else "",
                "extracted_text": raw.get("text_content") or "", "status": asset.get("status") or "ready",
            })
        elif usage == "result":
            assets.append(_asset_payload(asset))
    board = content.get("storyboard")
    if isinstance(board, dict) and board.get("id"):
        with repo.db.transaction() as conn:
            current = conn.execute("SELECT * FROM storyboards WHERE id=?", (board["id"],)).fetchone()
            current_shots = conn.execute(
                "SELECT * FROM storyboard_shots WHERE storyboard_id=? ORDER BY ordinal", (board["id"],),
            ).fetchall() if current else []
        if current:
            board = {**dict(current), "shots": [dict(item) | {"payload": json.loads(item["payload_json"] or "{}")} for item in current_shots]}
    storyboard = _storyboard_payload(repo, board, content.get("estimated_video_units")) if isinstance(board, dict) else None
    return {
        "id": message["id"], "conversation_id": message["conversation_id"],
        "role": "user" if message.get("role") in {"user", "client"} else message.get("role", "assistant"),
        "kind": message.get("kind") or "text", "text": message.get("content_text") or "",
        "attachments": attachments, "assets": assets, "storyboard": storyboard,
        "task_id": content.get("task_id") or "", "created_at": message.get("created_at"),
    }


def _task_payload(task: dict[str, Any], queue_position: int | None = None) -> dict[str, Any]:
    internal_status = task.get("status")
    status = {
        "planning": "running", "generating": "running", "assembling": "running",
        "waiting_approval": "waiting_confirmation",
    }.get(internal_status, internal_status)
    stage = str(task.get("stage") or "queued")
    if stage.startswith("镜头"):
        display_stage = "镜头生成"
    else:
        display_stage = STAGE_MAP.get(stage, stage)
    result = _public_projection(task.get("result") or {})
    result_storyboard = result.get("storyboard") if isinstance(result, dict) else None
    storyboard_id = result_storyboard.get("id") if isinstance(result_storyboard, dict) else None
    params = task.get("params") or {}
    return {
        "id": task["id"], "conversation_id": task["conversation_id"], "title": task.get("title") or "生产任务",
        "tool": TOOL_REVERSE.get(task.get("kind"), "create_video"), "status": status,
        "stage": display_stage, "progress": round(float(task.get("progress") or 0) * 100),
        "queue_position": queue_position, "eta_seconds": (queue_position or 0) * 45 if queue_position else None,
        "error_message": task.get("error_message") or "",
        "asset_ids": list(params.get("asset_ids") or []),
        "params": {key: params[key] for key in ("duration_seconds", "batch_count") if key in params},
        "result": result, "storyboard_id": storyboard_id,
        "heartbeat_at": task.get("updated_at"),
        "created_at": task.get("created_at"), "updated_at": task.get("updated_at"),
        "version": task.get("version"),
    }


def _batch_count(text: str) -> int:
    match = re.search(r"(?:批量|生成|做)?\s*(\d{1,2})\s*(?:条|个|版|组)", text)
    return max(1, min(20, int(match.group(1)))) if match else 3


def _replacement_params(text: str, duration_seconds: int | None) -> dict[str, Any]:
    interval = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|~|到|至)\s*(\d+(?:\.\d+)?)\s*秒", text)
    start = float(interval.group(1)) if interval else 0.0
    end = float(interval.group(2)) if interval else float(duration_seconds or 5)
    targets = (("声音", "声音"), ("音色", "声音"), ("人物", "人物"), ("人脸", "人物"),
               ("商品", "商品"), ("产品", "商品"), ("物品", "物品"), ("场景", "场景"), ("背景", "场景"))
    target = next((label for keyword, label in targets if keyword in text), "指定元素")
    return {"replace_start": max(0.0, start), "replace_end": max(start + 4, end), "replace_target": target}


def _record_asset_action(request: Request, asset: dict[str, Any], action: EventAction) -> None:
    if asset.get("media_type") not in {"image", "video"}:
        return
    metadata = asset.get("metadata") or {}
    task = _repo(request).get_task(str(metadata.get("task_id") or ""), client_id=asset["client_id"])
    params = (task or {}).get("params") or {}
    request.app.state.events.write(EventRecord(
        ts=datetime.now(timezone.utc), access_code=asset["client_id"], mode=Mode(asset["media_type"]),
        preset_id=(task or {}).get("kind") or "asset", template_version="chat-os-v2",
        prompt_user=str(params.get("prompt") or ""), prompt_final=str(params.get("prompt") or ""), params=params,
        model="gpt-image-2" if asset["media_type"] == "image" else "seedance2.0fast_vip",
        result_url=asset.get("storage_uri") or asset.get("source_url"), cost_units=0, action=action,
        job_id=(task or {}).get("id") or asset["id"], client_id=asset["client_id"],
        queue_name=asset["media_type"], provider_attempt=1,
    ))
    with _repo(request).db.transaction(immediate=True) as conn:
        conn.execute(
            """INSERT INTO activity_events(ts,client_id,event_type,conversation_id,task_id,asset_id,
            payload_json) VALUES(?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), asset["client_id"], f"asset.{action.value}",
             (task or {}).get("conversation_id"), (task or {}).get("id"), asset["id"], "{}"),
        )


async def _persist_ingested(request: Request, content: IngestedContent, client_id: str, source_type: str) -> dict[str, Any]:
    provider = request.app.state.provider
    uri = await provider.upload_attachment(
        content.filename, content.content, content.content_type,
        stage="attachment.upload", request_id=f"asset-{uuid4().hex}",
    )
    asset = _repo(request).create_asset(
        client_id=client_id, source_type=source_type, media_type=content.media_kind,
        filename=content.filename, mime_type=content.content_type, storage_uri=uri,
        source_url=content.source_url, byte_size=content.size_bytes, status="ready", metadata=content.metadata,
    )
    if content.parsed_text:
        now = datetime.now(timezone.utc).isoformat()
        with _repo(request).db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT INTO asset_extractions(id,asset_id,parser_name,parser_version,status,text_content,
                structured_json,created_at,finished_at) VALUES(?,?,?,'1','succeeded',?,'{}',?,?)""",
                (uuid4().hex, asset["id"], "hook-ingestion", content.parsed_text, now, now),
            )
    return asset


def _crawler_target(data: Any) -> str | None:
    if isinstance(data, str) and data.startswith("http"):
        return data
    if isinstance(data, dict):
        for key in ("download_url", "play_url", "media_url", "url"):
            value = data.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        for value in data.values():
            found = _crawler_target(value)
            if found:
                return found
    if isinstance(data, list):
        for value in data:
            found = _crawler_target(value)
            if found:
                return found
    return None


async def _ingest_link(request: Request, url: str, client_id: str) -> dict[str, Any]:
    settings = request.app.state.settings
    host = (urlsplit(url).hostname or "").lower()
    platform = next((name for name in ("youtube", "tiktok", "douyin", "bilibili") if name in host), None)
    source_url = url
    if platform and settings.crawler_api_key:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{settings.crawler_base_url}/{platform}/video_url",
                headers={"X-API-Key": settings.crawler_api_key}, json={"url": url},
            )
            response.raise_for_status()
            source_url = _crawler_target(response.json()) or url
    content = await request.app.state.ingestion.ingest_url(source_url)
    if source_url != url:
        content = IngestedContent(
            filename=content.filename, content_type=content.content_type, media_kind=content.media_kind,
            size_bytes=content.size_bytes, content=content.content, parsed_text=content.parsed_text,
            source_url=url, metadata={**content.metadata, "resolved_media_url": source_url, "platform": platform},
        )
    return await _persist_ingested(request, content, client_id, "link")


class ConversationInput(BaseModel):
    title: str = Field(default="新对话", max_length=120)


class StoryboardDecision(BaseModel):
    approved: bool
    feedback: str = Field(default="", max_length=4000)


class BatchDownloadInput(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)


class ShotPatch(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    duration_seconds: float | None = Field(default=None, ge=4, le=15)
    story_function: str | None = Field(default=None, max_length=1000)
    visual: str | None = Field(default=None, max_length=4000)
    shot_size: str | None = Field(default=None, max_length=120)
    camera_angle: str | None = Field(default=None, max_length=120)
    camera_height: str | None = Field(default=None, max_length=120)
    lens_feel: str | None = Field(default=None, max_length=120)
    composition: str | None = Field(default=None, max_length=2000)
    action_start: str | None = Field(default=None, max_length=2000)
    action_trigger: str | None = Field(default=None, max_length=2000)
    action_result: str | None = Field(default=None, max_length=2000)
    camera_move: str | None = Field(default=None, max_length=1000)
    sound: str | None = Field(default=None, max_length=1000)
    transition: str | None = Field(default=None, max_length=1000)
    stable_truth: list[str] | None = Field(default=None, max_length=20)
    may_vary: list[str] | None = Field(default=None, max_length=20)
    reference_manifest: list[dict[str, Any]] | None = Field(default=None, max_length=12)
    first_failure_cue: str | None = Field(default=None, max_length=2000)


class PanelRegenerateInput(BaseModel):
    expected_version: int = Field(ge=1)
    feedback: str = Field(default="", max_length=4000)


class CandidateSelectInput(BaseModel):
    expected_version: int = Field(ge=1)


class ScopedDecisionInput(BaseModel):
    expected_version: int = Field(ge=1)
    scope: str
    target_id: str = ""
    scope_id: str = ""
    decision: str
    feedback: str = Field(default="", max_length=4000)
    idempotency_key: str | None = Field(default=None, max_length=160)


class AnimaticInput(BaseModel):
    expected_version: int = Field(ge=1)
    confirm: bool = False


class ProduceInput(BaseModel):
    expected_version: int = Field(ge=1)


@router.get("/bootstrap")
async def bootstrap(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    client_id = str(_value(principal, "code_id"))
    repo = _repo(request)
    video = repo.quota_snapshot(
        client_id=client_id, resource="video", client_limit=int(_value(principal, "daily_video_limit", 100)),
        global_limit=request.app.state.settings.global_video_daily_limit,
    )
    image = repo.quota_snapshot(
        client_id=client_id, resource="image", client_limit=int(_value(principal, "daily_image_limit", 1000)),
        global_limit=request.app.state.settings.global_image_daily_limit,
    )
    return {"usage": {
        "global_video_used": video["global_used"], "global_video_limit": video["global_limit"],
        "client_video_used": video["client_used"], "client_video_limit": video["client_limit"],
        "image_used": image["client_used"], "image_limit": image["client_limit"],
        "reset_at": next_reset_at().isoformat(),
    }, "queues": await request.app.state.production.snapshot(),
        # Legacy clients may still read this field; the v2 interface does not render presets.
        "presets": request.app.state.presets,
    }


@router.get("/conversations")
async def conversations(request: Request) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    items = _repo(request).list_conversations(client_id)
    with _repo(request).db.transaction() as conn:
        for item in items:
            row = conn.execute(
                "SELECT content_text FROM messages WHERE conversation_id=? ORDER BY seq DESC LIMIT 1", (item["id"],),
            ).fetchone()
            item["last_message"] = row["content_text"] if row else ""
            item["unread_count"] = 0
    return {"items": items}


@router.post("/conversations")
async def create_conversation(payload: ConversationInput, request: Request) -> dict[str, Any]:
    return _repo(request).create_conversation(client_id=str(_value(_principal(request), "code_id")), title=payload.title)


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, payload: ConversationInput, request: Request) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    with _repo(request).db.transaction(immediate=True) as conn:
        cursor = conn.execute(
            "UPDATE conversations SET title=?,updated_at=? WHERE id=? AND client_id=? AND deleted_at IS NULL",
            (payload.title.strip() or "新对话", datetime.now(timezone.utc).isoformat(), conversation_id, client_id),
        )
    if cursor.rowcount != 1:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "对话不存在"})
    return _repo(request).get_conversation(conversation_id, client_id=client_id) or {}


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, request: Request) -> None:
    if not _repo(request).delete_conversation(conversation_id, client_id=str(_value(_principal(request), "code_id"))):
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "对话不存在"})


@router.get("/conversations/{conversation_id}/messages")
async def messages(conversation_id: str, request: Request) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    rows = _repo(request).list_messages(conversation_id, client_id=client_id, limit=500)
    return {"items": [_message_payload(_repo(request), row) for row in rows]}


@router.post("/conversations/{conversation_id}/messages", status_code=202)
async def send_message(
    conversation_id: str, request: Request,
    text: str = Form(default=""), tool: str = Form(default="create_video"),
    duration_seconds: int | None = Form(default=None), links: str = Form(default="[]"),
    attachments: list[UploadFile] = File(default=[]),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    principal = _principal(request); client_id = str(_value(principal, "code_id")); repo = _repo(request)
    if tool not in TOOL_MAP:
        raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "不支持的生产工具"})
    declared_kind = TOOL_MAP[tool][0]
    if declared_kind in {"create", "replicate", "batch"}:
        if duration_seconds is None:
            raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "请先确认视频总时长（4-60秒）"})
        if duration_seconds < 4 or duration_seconds > 60:
            raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "视频总时长必须为4-60秒"})
    normalized_key = (idempotency_key or "").strip()
    if normalized_key and (len(normalized_key) < 8 or len(normalized_key) > 160 or not re.fullmatch(r"[A-Za-z0-9._:-]+", normalized_key)):
        raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "提交标识格式无效"})
    if normalized_key:
        replay = repo.get_idempotent_submission(
            client_id=client_id, conversation_id=conversation_id, idempotency_key=normalized_key,
        )
        if replay:
            return {
                "message": _message_payload(repo, replay["message"]),
                "task": _task_payload(replay["task"]),
                "replayed": True,
            }
    try:
        parsed_links = json.loads(links or "[]")
        if not isinstance(parsed_links, list) or len(parsed_links) > 10:
            raise ValueError("单次最多解析10个链接")
        assets: list[dict[str, Any]] = []
        for upload in attachments:
            content = await request.app.state.ingestion.ingest_stream(
                upload.filename or "attachment.bin", upload.file, upload.content_type,
            )
            assets.append(await _persist_ingested(request, content, client_id, "upload"))
        for url in parsed_links:
            assets.append(await _ingest_link(request, str(url), client_id))
        if not text.strip() and not assets:
            raise ValueError("请输入需求或添加素材")
        message = repo.add_message(
            conversation_id, role="user", content_text=text.strip(), kind="text",
            content={"tool": tool, "duration_seconds": duration_seconds}, client_id=client_id,
        )
        for index, asset in enumerate(assets):
            repo.bind_asset(message["id"], asset["id"], usage="input", ordinal=index, client_id=client_id)
        kind, title = TOOL_MAP[tool]
        image_assets = [asset for asset in assets if asset.get("media_type") == "image"]
        video_assets = [asset for asset in assets if asset.get("media_type") == "video"]
        if kind == "replace" and video_assets and not image_assets and re.search(r"声音|音色|配音|口播|voice|audio", text, re.I):
            kind, title = "voice_replace", "声音替换"
        params = {
            "prompt": text.strip(), "asset_ids": [item["id"] for item in assets],
            "duration_seconds": duration_seconds, "batch_count": _batch_count(text) if kind == "batch" else 1,
            "client_video_limit": int(_value(principal, "daily_video_limit", 100)),
            "client_image_limit": int(_value(principal, "daily_image_limit", 1000)),
        }
        if kind == "replace":
            params.update(_replacement_params(text, duration_seconds))
        if kind == "voice_replace":
            params["voice_text"] = text.strip()
        task = repo.create_task(
            client_id=client_id, conversation_id=conversation_id, kind=kind, title=title,
            request_message_id=message["id"], params=params,
        )
        if normalized_key:
            recorded = repo.record_idempotent_submission(
                client_id=client_id, conversation_id=conversation_id,
                idempotency_key=normalized_key, message_id=message["id"], task_id=task["id"],
            )
            if recorded.get("task_id") != task["id"]:
                replay = repo.get_idempotent_submission(
                    client_id=client_id, conversation_id=conversation_id, idempotency_key=normalized_key,
                )
                if replay:
                    return {
                        "message": _message_payload(repo, replay["message"]),
                        "task": _task_payload(replay["task"]),
                        "replayed": True,
                    }
        await request.app.state.production.enqueue(task["id"])
        return {"message": _message_payload(repo, message), "task": _task_payload(task, 1), "replayed": False}
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/storyboards/{storyboard_id}/confirm")
async def confirm_storyboard(storyboard_id: str, payload: StoryboardDecision, request: Request) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    with _repo(request).db.transaction() as conn:
        row = conn.execute(
            """SELECT s.task_id,t.version FROM storyboards s JOIN task_runs t ON t.id=s.task_id
            WHERE s.id=? AND t.client_id=?""", (storyboard_id, client_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "故事板不存在"})
    try:
        task = await request.app.state.production.confirm(
            row["task_id"], client_id=client_id, expected_version=int(row["version"]),
            approve=payload.approved, note=payload.feedback,
        )
        with _repo(request).db.transaction(immediate=True) as conn:
            conn.execute("UPDATE storyboards SET status=? WHERE id=?", ("confirmed" if payload.approved else "revision_required", storyboard_id))
        return {"task": _task_payload(task)}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/storyboards/{storyboard_id}")
async def storyboard_detail(storyboard_id: str, request: Request) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    board = _repo(request).get_storyboard(storyboard_id, client_id=client_id)
    if board is None:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "故事板不存在"})
    return _storyboard_payload(_repo(request), board)


@router.patch("/storyboards/{storyboard_id}/shots/{shot_id}")
async def patch_storyboard_shot(
    storyboard_id: str, shot_id: str, payload: ShotPatch, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    values = payload.model_dump(exclude={"expected_version"}, exclude_none=True)
    try:
        board = _repo(request).patch_storyboard_shot(
            storyboard_id, shot_id, client_id=client_id,
            expected_version=payload.expected_version, values=values,
        )
        return _storyboard_payload(_repo(request), board)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/storyboards/{storyboard_id}/shots/{shot_id}/regenerate")
async def regenerate_storyboard_shot(
    storyboard_id: str, shot_id: str, payload: PanelRegenerateInput, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    try:
        board = await request.app.state.production.regenerate_shot(
            storyboard_id, shot_id, client_id=client_id,
            expected_version=payload.expected_version, feedback=payload.feedback,
        )
        return _storyboard_payload(_repo(request), board)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/storyboards/{storyboard_id}/panels/{panel_id}/regenerate")
async def regenerate_storyboard_panel(
    storyboard_id: str, panel_id: str, payload: PanelRegenerateInput, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    try:
        board = await request.app.state.production.regenerate_panel(
            storyboard_id, panel_id, client_id=client_id,
            expected_version=payload.expected_version, feedback=payload.feedback,
        )
        return _storyboard_payload(_repo(request), board)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/storyboards/{storyboard_id}/panels/{panel_id}/candidates")
async def storyboard_panel_candidates(
    storyboard_id: str, panel_id: str, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    try:
        history = _repo(request).list_panel_candidates(
            storyboard_id, panel_id, client_id=client_id,
        )
        candidates = []
        for candidate in history["candidates"]:
            selected = _repo(request).get_asset(
                str(candidate.get("selected_asset_id") or ""), client_id=client_id,
            )
            annotated = _repo(request).get_asset(
                str(candidate.get("annotated_asset_id") or ""), client_id=client_id,
            )
            candidates.append({
                "id": candidate["id"], "revision": int(candidate.get("revision") or 1),
                "logical_key": candidate.get("logical_key"), "order": candidate.get("ordinal"),
                "role": "end" if candidate.get("role") == "result" else candidate.get("role"),
                "description": candidate.get("description") or "",
                "clean_asset_id": candidate.get("clean_asset_id"),
                "selected_asset_id": candidate.get("selected_asset_id"),
                "clean_url": _sendable_asset_url(selected),
                "annotated_url": _sendable_asset_url(annotated),
                "send_to_provider": bool(candidate.get("send_to_provider")),
                "is_current": bool(candidate.get("is_current")),
                "created_at": candidate.get("created_at"),
            })
        return {**{key: value for key, value in history.items() if key != "candidates"}, "candidates": candidates}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/storyboards/{storyboard_id}/panels/{panel_id}/candidates/{candidate_id}/select")
async def select_storyboard_panel_candidate(
    storyboard_id: str, panel_id: str, candidate_id: str,
    payload: CandidateSelectInput, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    try:
        board = _repo(request).select_panel_candidate(
            storyboard_id, panel_id, candidate_id, client_id=client_id,
            expected_version=payload.expected_version,
        )
        return _storyboard_payload(_repo(request), board)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/storyboards/{storyboard_id}/decisions")
async def storyboard_decision(
    storyboard_id: str, payload: ScopedDecisionInput, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    try:
        scope = "board" if payload.scope == "storyboard" else payload.scope
        target_id = payload.target_id or payload.scope_id
        if scope == "animatic" and payload.decision == "approved":
            board = _repo(request).confirm_animatic(
                storyboard_id, client_id=client_id, expected_version=payload.expected_version,
            )
        else:
            _repo(request).record_approval(
                storyboard_id=storyboard_id, client_id=client_id, scope=scope,
                target_id=target_id, decision=payload.decision,
                expected_version=payload.expected_version, feedback=payload.feedback,
                idempotency_key=payload.idempotency_key,
            )
            board = _repo(request).get_storyboard(storyboard_id, client_id=client_id)
            assert board is not None
        return _storyboard_payload(_repo(request), board)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/storyboards/{storyboard_id}/animatic")
async def create_storyboard_animatic(
    storyboard_id: str, payload: AnimaticInput, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    try:
        board = await request.app.state.production.create_animatic(
            storyboard_id, client_id=client_id, expected_version=payload.expected_version,
            confirm=payload.confirm,
        )
        return _storyboard_payload(_repo(request), board)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/storyboards/{storyboard_id}/produce", status_code=202)
async def produce_storyboard(
    storyboard_id: str, payload: ProduceInput, request: Request,
) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    try:
        task = await request.app.state.production.produce(
            storyboard_id, client_id=client_id, expected_version=payload.expected_version,
        )
        return {"task": _task_payload(task)}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/tasks")
async def tasks(request: Request, conversation_id: str | None = None) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id"))
    rows = _repo(request).list_tasks(client_id, conversation_id=conversation_id, limit=500)
    queued = [row for row in reversed(rows) if row.get("status") == "queued"]
    positions = {row["id"]: index + 1 for index, row in enumerate(queued)}
    return {"items": [_task_payload(row, positions.get(row["id"])) for row in rows]}


@router.get("/tasks/{task_id}")
async def task(task_id: str, request: Request) -> dict[str, Any]:
    row = _repo(request).get_task(task_id, client_id=str(_value(_principal(request), "code_id")))
    if not row:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "任务不存在"})
    return _task_payload(row)


@router.get("/tasks/{task_id}/events")
async def task_events(
    task_id: str, request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    client_id = str(_value(_principal(request), "code_id"))
    if _repo(request).get_task(task_id, client_id=client_id) is None:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "任务不存在"})
    try:
        cursor = int(last_event_id or 0)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "Last-Event-ID无效"}) from exc
    return StreamingResponse(
        request.app.state.workflow_events.iter_sse(task_id, client_id=client_id, last_event_id=cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    client_id = str(_value(_principal(request), "code_id")); repo = _repo(request)
    row = repo.get_task(task_id, client_id=client_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "任务不存在"})
    if row["status"] not in {"queued", "waiting_approval"}:
        raise HTTPException(status_code=409, detail={"error_code": "TASK_RUNNING", "message": "供应商已开始执行，当前不能安全取消"})
    for resource in ("image", "video"):
        try:
            repo.release(task_id=task_id, resource=resource, client_id=client_id)
        except Exception:
            pass
    updated = repo.update_task(task_id, {"status": "cancelled", "stage": "cancelled", "finished_at": datetime.now(timezone.utc).isoformat()})
    return _task_payload(updated)


@router.post("/assets/batch-download")
async def batch_download(payload: BatchDownloadInput, request: Request) -> dict[str, str]:
    client_id = str(_value(_principal(request), "code_id")); repo = _repo(request)
    assets = [repo.get_asset(asset_id, client_id=client_id) for asset_id in payload.asset_ids]
    if not all(assets):
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "部分产物不存在"})
    bundle_id = uuid4().hex
    directory = request.app.state.settings.data_dir / "downloads" / client_id
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f"{bundle_id}.zip"
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for index, asset in enumerate(assets, start=1):
                assert asset is not None
                url = _sendable_asset_url(asset)
                if not url:
                    raise HTTPException(
                        status_code=404,
                        detail={"error_code": "NOT_FOUND", "message": "部分产物尚未就绪或地址无效"},
                    )
                response = await client.get(url)
                response.raise_for_status()
                suffix = Path(urlsplit(url).path).suffix or (".mp4" if asset.get("media_type") == "video" else ".png")
                output.writestr(f"{index:02d}-{asset.get('filename') or asset['id']}{suffix if not str(asset.get('filename') or '').endswith(suffix) else ''}", response.content)
                _record_asset_action(request, asset, EventAction.DOWNLOAD)
    return {"download_url": f"{request.app.state.settings.base_path}/api/studio/downloads/{bundle_id}"}


@router.get("/downloads/{bundle_id}")
async def download_bundle(bundle_id: str, request: Request) -> FileResponse:
    if not re.fullmatch(r"[a-f0-9]{32}", bundle_id):
        raise HTTPException(status_code=404)
    client_id = str(_value(_principal(request), "code_id"))
    path = request.app.state.settings.data_dir / "downloads" / client_id / f"{bundle_id}.zip"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "下载包不存在或已清理"})
    return FileResponse(path, media_type="application/zip", filename="hook-studio-results.zip")


@router.get("/assets/{asset_id}/download")
async def download_asset(asset_id: str, request: Request) -> RedirectResponse:
    asset = _repo(request).get_asset(asset_id, client_id=str(_value(_principal(request), "code_id")))
    url = _sendable_asset_url(asset)
    if not asset or not url:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "产物不存在"})
    _record_asset_action(request, asset, EventAction.DOWNLOAD)
    return RedirectResponse(url, status_code=307)


@router.get("/assets/{asset_id}/preview")
async def preview_asset(asset_id: str, request: Request) -> RedirectResponse:
    asset = _repo(request).get_asset(asset_id, client_id=str(_value(_principal(request), "code_id")))
    url = _sendable_asset_url(asset)
    if not asset or not url:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "产物不存在"})
    _record_asset_action(request, asset, EventAction.PREVIEW)
    return RedirectResponse(url, status_code=307)
