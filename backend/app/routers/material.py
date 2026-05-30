"""素材生产 generation (MOCK). Job id encodes the start time + a tab code so
/jobs/{id} can report progress and the result kind (audio vs video) statelessly.
Swap the mocked branches for real providers (Seedance / TTS / digital-human)."""
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

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


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


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
        return {
            "ok": True,
            "job": {"id": job_id, "status": "processing", "progress": progress},
        }

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
