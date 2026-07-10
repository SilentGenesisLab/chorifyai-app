from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.services.generation import GenerationCommand, GenerationFailure

router = APIRouter(prefix="/api/studio", tags=["studio"])

PRESET_TEMPLATES = {
    "pain-point": "美区TikTok真实家庭场景，首秒近景展示用户痛点；当产品进入画面后，立刻用一个明确动作解决问题，随后展示可验证结果。保持真实材质、自然手持镜头、9:16构图。",
    "visual-impact": "美区TikTok竖屏实拍，首秒用明确的尺度、速度或材质变化形成强视觉停留；当产品进入画面后，随后完成一个真实可复现动作并展示结果。9:16近景。",
    "suspense": "美区TikTok真实使用场景，首秒只揭示异常细节制造悬念；当镜头推进后，产品自然出现并完成一个可理解动作，随后揭示原因和结果。9:16。",
    "contrast": "美区TikTok竖屏实拍，同一场景明确呈现使用前后对比；当产品完成核心动作后，随后切到同角度结果镜头，光线与尺度连续。9:16。",
    "use-scene": "美区消费者真实日常环境，手部自然拿起并使用产品；当动作触发核心功能后，随后展示结果，镜头克制、材质真实、无广告棚拍感。9:16。",
    "handheld-proof": "美区TikTok手持证明镜头，单手拿稳产品并以近景展示细节；随后完成一个真实可复现的操作动作，同时保留自然手部微动。9:16。",
}


def _principal(request: Request) -> Any:
    principal = getattr(request.state, "session", None) or getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail={"error_code": "AUTH_REQUIRED", "message": "请先输入访问码"})
    return getattr(principal, "principal", principal)


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _service(request: Request) -> Any:
    service = getattr(request.app.state, "generation_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail={"error_code": "INTERNAL_ERROR", "message": "生成服务尚未就绪"})
    return service


@router.get("/bootstrap")
async def bootstrap(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    presets = getattr(request.app.state, "presets", None) or [
        {"id": key, "label": label, "version": "1.0.0", "cost_units": {"image": 0, "video": 1}}
        for key, label in zip(PRESET_TEMPLATES, ("痛点直击", "强视觉开场", "悬念开场", "对比冲击", "真实使用场景", "手持动作证明"))
    ]
    quota = getattr(request.app.state, "quota", None)
    usage = None
    if quota is not None:
        usage = quota.snapshot(_get(principal, "code_id"), int(_get(principal, "daily_video_limit", 100)))
        usage = usage.model_dump(mode="json") if hasattr(usage, "model_dump") else usage
    return {"principal": principal, "presets": presets, "usage": usage, "video_daily_limit": 100, "image_unlimited": True}


@router.post("/jobs", status_code=202)
async def create_job(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    form = await request.form()
    mode = str(form.get("mode", ""))
    preset_id = str(form.get("preset_id", ""))
    prompt_user = str(form.get("prompt_user", "")).strip()
    duration = int(form.get("duration") or 4)
    if mode not in {"image", "video"} or preset_id not in PRESET_TEMPLATES or not prompt_user:
        raise HTTPException(status_code=422, detail={"error_code": "INPUT_INVALID", "message": "请选择模式、预设并填写产品描述"})
    service = _service(request)
    reference_urls: list[str] = []
    reference = form.get("reference")
    if reference is not None and getattr(reference, "filename", None):
        content = await reference.read()
        uri = await service.provider.upload_reference(reference.filename, content, reference.content_type or "application/octet-stream", request_id=f"upload-{_get(principal, 'code_id')}-{int(datetime.now().timestamp())}")
        reference_urls.append(uri)
    prompt_final = f"{PRESET_TEMPLATES[preset_id]} 产品事实：{prompt_user}"
    if mode == "video":
        prompt_final += "。全片保留原生环境音和动作音，不配背景音乐，不出现字幕、水印或竞品logo。"
    manifest = [{"slot": index + 1, "url": url, "role": "产品身份与外观参考"} for index, url in enumerate(reference_urls)]
    try:
        job = await service.submit(GenerationCommand(client_id=_get(principal, "code_id"), client_video_limit=int(_get(principal, "daily_video_limit", 100)), mode=mode, preset_id=preset_id, template_version="1.0.0", prompt_user=prompt_user, prompt_final=prompt_final, duration=duration, reference_urls=reference_urls, slot_manifest=manifest))
    except GenerationFailure as exc:
        raise HTTPException(status_code=422, detail={"error_code": exc.code, "message": str(exc), "request_id": exc.request_id}) from exc
    queue = await service.queues.for_mode(mode).snapshot(job["id"])
    return {"job": job, "queue": queue}


async def _owned_job(request: Request, job_id: str) -> tuple[Any, dict[str, Any]]:
    principal = _principal(request)
    service = _service(request)
    job = await service.repository.get_job(job_id)
    if not job or job.get("client_id") != _get(principal, "code_id") or job.get("deleted_at"):
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "任务不存在"})
    return service, job


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    service, job = await _owned_job(request, job_id)
    queue = await service.queues.for_mode(job["mode"]).snapshot(job_id)
    return {"job": job, "queue": queue}


@router.get("/jobs")
async def list_jobs(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    jobs = await _service(request).repository.list_jobs(_get(principal, "code_id"))
    return {"items": jobs}


@router.get("/gallery")
async def gallery(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    jobs = await _service(request).repository.list_jobs(_get(principal, "code_id"), gallery_only=True)
    return {"items": jobs}


@router.post("/jobs/{job_id}/regenerate", status_code=202)
async def regenerate(job_id: str, request: Request) -> dict[str, Any]:
    service, job = await _owned_job(request, job_id)
    command = GenerationCommand(client_id=job["client_id"], client_video_limit=int(job.get("client_video_limit", 100)), mode=job["mode"], preset_id=job["preset_id"], template_version=job["template_version"], prompt_user=job["prompt_user"], prompt_final=job["prompt_final"], duration=int(job.get("duration", 4)), reference_urls=job.get("reference_urls", []), slot_manifest=job.get("slot_manifest", []))
    try:
        created = await service.submit(command)
    except GenerationFailure as exc:
        raise HTTPException(status_code=422, detail={"error_code": exc.code, "message": str(exc), "request_id": exc.request_id}) from exc
    await service._event("regenerate", job)
    return {"job": created}


@router.post("/jobs/{job_id}/preview")
async def preview(job_id: str, request: Request) -> dict[str, bool]:
    service, job = await _owned_job(request, job_id)
    await service._event("preview", job)
    return {"ok": True}


@router.get("/jobs/{job_id}/download")
async def download(job_id: str, request: Request) -> RedirectResponse:
    service, job = await _owned_job(request, job_id)
    if job.get("status") != "succeeded" or not job.get("result_url"):
        raise HTTPException(status_code=409, detail={"error_code": "RESULT_INVALID", "message": "产物尚未就绪"})
    await service._event("download", job)
    return RedirectResponse(job["result_url"], status_code=307)


@router.delete("/jobs/{job_id}")
async def delete(job_id: str, request: Request) -> dict[str, bool]:
    service, job = await _owned_job(request, job_id)
    await service.repository.update_job(job_id, {"deleted_at": datetime.now(timezone.utc).isoformat()})
    await service._event("delete", job)
    return {"ok": True}
