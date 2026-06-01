"""素材生产 generation.

AI影棚(ai_studio) 已接入真实 Seedance 视频生成（火山方舟 Ark，图生视频）：
上传产品图 → 自动运镜商品大片。其余 tab（replica/element_swap/digital_human）暂
为 mock 占位；配音(dubbing) 走 /api/voice。

异步 job：POST /generate 立即返回 job_id（仅提交，不等出片）；GET /jobs/{id}
轮询——真实影棚任务查 Seedance，其余按时间模拟进度。"""
import threading
import time
import uuid
from datetime import datetime, timezone

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from app.services import seedance
from app.services.oss import put_object

router = APIRouter(prefix="/api/material", tags=["material"])

GEN_MS = 4000
TAB_CODE = {
    "ai_studio": "s",
    "replica": "r",
    "element_swap": "e",
    "dubbing": "d",
    "digital_human": "h",
}
AUDIO_CODES = {"d"}  # 配音 → audio result

# AI影棚真实任务存储（内存，单进程 uvicorn 足够）：job_id -> {status, task_id, ...}
_JOBS: dict[str, dict] = {}

# 影棚默认运镜/卖点模板（自动出镜·自动运镜，用户无需写 prompt）
_STUDIO_PROMPT = (
    "High-end product commercial. Keep the product the clear hero, true to the "
    "reference image. Smooth cinematic camera move — slow push-in then a gentle "
    "orbit. Soft premium studio lighting, shallow depth of field, glossy reflections, "
    "clean modern set. Photoreal, crisp 4K detail, luxury advertising aesthetic."
)


_mirror_session = requests.Session()
_mirror_session.trust_env = False


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _mirror_to_oss(video_url: str) -> str:
    """Seedance 输出是 24h 过期的临时 URL —— 转存到本平台 OSS 拿永久链接。"""
    r = _mirror_session.get(video_url, timeout=180)
    r.raise_for_status()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"studio/{day}/{uuid.uuid4().hex}.mp4"
    return put_object(key, r.content, "video/mp4")


def _finalize(job_id: str, video_url: str) -> None:
    """后台把 Seedance 临时视频转存到本平台 OSS，完成后置 succeeded。"""
    job = _JOBS.get(job_id)
    if job is None:
        return
    try:
        job["resultUrl"] = _mirror_to_oss(video_url)
    except Exception as e:  # noqa: BLE001 — 转存失败回退临时 URL（仍可播放 24h）
        print(f"[material] 转存 OSS 失败，回退临时 URL：{e}")
        job["resultUrl"] = video_url
    job["status"] = "succeeded"


class GenerateRequest(BaseModel):
    tab: str = "ai_studio"
    settings: dict | None = None
    source_url: str | None = None
    refs: list[str] | None = None
    prompt: str | None = None
    voice: str | None = None
    ip: str | None = None
    duration: int | None = None


@router.post("/generate")
def generate(req: GenerateRequest):
    ms = int(time.time() * 1000)
    code = TAB_CODE.get(req.tab, "s")
    job_id = f"job_{ms}_{code}_{uuid.uuid4().hex[:6]}"

    # AI影棚 → 真实 Seedance 图生视频
    if req.tab == "ai_studio":
        s = req.settings or {}
        ratio = str(s.get("ratio") or "9:16")
        resolution = str(s.get("resolution") or "720p")
        duration = int(req.duration or s.get("duration") or 5)
        prompt = (req.prompt or "").strip() or _STUDIO_PROMPT
        try:
            task_id = seedance.submit(
                prompt,
                req.source_url,
                ratio=ratio,
                resolution=resolution,
                duration=duration,
            )
            _JOBS[job_id] = {
                "status": "processing",
                "task_id": task_id,
                "kind": "video",
                "durationSec": duration,
            }
        except Exception as e:  # noqa: BLE001 — 提交失败也回 job，轮询时报 failed
            print(f"[material] Seedance 提交失败：{e}")
            _JOBS[job_id] = {"status": "failed", "kind": "video", "error": str(e)}
        return {
            "ok": True,
            "job": {
                "id": job_id,
                "type": req.tab,
                "status": "processing",
                "progress": 0,
                "createdAt": _iso(ms),
            },
        }

    # 其余 tab：mock 占位
    return {
        "ok": True,
        "job": {
            "id": job_id,
            "type": req.tab,
            "status": "processing",
            "progress": 0,
            "createdAt": _iso(ms),
        },
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    # 真实影棚任务：查 Seedance
    job = _JOBS.get(job_id)
    if job is not None:
        if job["status"] == "succeeded":
            return {
                "ok": True,
                "job": {
                    "id": job_id,
                    "status": "succeeded",
                    "progress": 100,
                    "kind": "video",
                    "resultUrl": job.get("resultUrl"),
                    "durationSec": job.get("durationSec"),
                },
            }
        if job["status"] == "failed":
            return {
                "ok": True,
                "job": {"id": job_id, "status": "failed", "progress": 0, "error": job.get("error")},
            }
        # processing → 轮询 Ark
        try:
            t = seedance.get_task(job["task_id"])
        except Exception as e:  # noqa: BLE001 — 瞬时查询失败，保持 processing 继续轮询
            print(f"[material] 查询 Seedance 失败（继续轮询）：{e}")
            return {"ok": True, "job": {"id": job_id, "status": "processing", "progress": 40}}
        st = t.get("status")
        if st == "succeeded" and t.get("video_url"):
            # 首次出片：后台转存到本平台 OSS 拿永久链接，转存期间先报 processing
            if not job.get("finalizing"):
                job["finalizing"] = True
                threading.Thread(
                    target=_finalize, args=(job_id, t["video_url"]), daemon=True
                ).start()
            return {"ok": True, "job": {"id": job_id, "status": "processing", "progress": 92}}
        if st in ("failed", "cancelled"):
            job["status"] = "failed"
            job["error"] = t.get("error") or st
            return {"ok": True, "job": {"id": job_id, "status": "failed", "progress": 0, "error": job["error"]}}
        # queued / running
        progress = 20 if st == "queued" else 65
        return {"ok": True, "job": {"id": job_id, "status": "processing", "progress": progress}}

    # mock（其余 tab）：按时间模拟进度
    parts = job_id.split("_")
    started = (
        int(parts[1])
        if len(parts) > 1 and parts[1].isdigit()
        else int(time.time() * 1000) - GEN_MS
    )
    code = parts[2] if len(parts) > 2 else "s"
    kind = "audio" if code in AUDIO_CODES else "video"

    elapsed = int(time.time() * 1000) - started
    if elapsed < GEN_MS:
        progress = max(5, min(95, int(elapsed / GEN_MS * 100)))
        return {"ok": True, "job": {"id": job_id, "status": "processing", "progress": progress}}

    h = sum(ord(c) for c in job_id)
    duration = 5 if kind == "video" else 6 + (h % 24)
    return {
        "ok": True,
        "job": {
            "id": job_id,
            "status": "succeeded",
            "progress": 100,
            "kind": kind,
            "durationSec": duration,
            "thumbnailUrl": None,
            "resultUrl": None,
            "createdAt": _iso(started),
        },
    }
