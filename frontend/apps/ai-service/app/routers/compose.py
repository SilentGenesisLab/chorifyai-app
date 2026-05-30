"""合成量产 — 智能混剪 / 超级混剪 / 一键成片 (mocked)."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/api/compose", tags=["compose"])


class MixRequest(BaseModel):
    project_id: str
    count: int = 5


class Combo(BaseModel):
    combo_id: str
    status: str
    preview_url: str | None = None


class MixResponse(BaseModel):
    project_id: str
    combos: list[Combo]


@router.post("/mix", response_model=MixResponse)
def mix(req: MixRequest) -> MixResponse:
    """Produce N mixed video combinations. Mock returns placeholders."""
    if not settings.mock_mode:
        raise NotImplementedError("real ffmpeg/render pipeline not wired yet")

    combos = [
        Combo(
            combo_id=f"combo_{uuid.uuid4().hex[:8]}",
            status="succeeded",
            preview_url=f"https://mock-oss.local/combos/{req.project_id}_{i}.mp4",
        )
        for i in range(max(1, min(req.count, 50)))
    ]
    return MixResponse(project_id=req.project_id, combos=combos)
