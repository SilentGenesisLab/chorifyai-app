"""素材生产 — AI 影棚 / AI 复刻 / 元素替换 / 配音 / 数字人 (mocked)."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/api/material", tags=["material"])


class GenerateRequest(BaseModel):
    type: str  # ai_studio | replica | element_swap | dubbing | digital_human
    prompt: str | None = None
    image_url: str | None = None
    options: dict | None = None


class Job(BaseModel):
    job_id: str
    status: str  # queued | running | succeeded | failed
    type: str
    result_url: str | None = None


@router.post("/generate", response_model=Job)
def generate(req: GenerateRequest) -> Job:
    """Kick off a generation job. Mock returns a queued job id."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    if settings.mock_mode:
        return Job(job_id=job_id, status="queued", type=req.type)
    # TODO: dispatch to real provider (Seedance / TTS / digital-human)
    raise NotImplementedError("real providers not wired yet")


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    """Poll a job. Mock always reports success with a placeholder asset."""
    if settings.mock_mode:
        return Job(
            job_id=job_id,
            status="succeeded",
            type="ai_studio",
            result_url=f"https://mock-oss.local/generated/{job_id}.mp4",
        )
    raise NotImplementedError("real providers not wired yet")
