from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.providers.kernel import ProviderResult


class FakeKernelProvider:
    """Zero-cost deterministic provider used only by local tests and Playwright."""

    async def upload_reference(self, filename: str, content: bytes, content_type: str, *, request_id: str | None = None) -> str:
        return f"https://example.invalid/reference/{request_id or uuid4().hex}/{filename}"

    async def upload_attachment(self, filename: str, content, content_type: str, *, max_bytes: int = 1024 * 1024 * 1024, stage: str = "attachment.upload", request_id: str | None = None) -> str:
        return f"https://example.invalid/attachment/{request_id or uuid4().hex}/{filename}"

    async def upload_blob(self, filename: str, content: bytes, content_type: str, *, stage: str, request_id: str | None = None) -> str:
        return f"https://example.invalid/output/{request_id or uuid4().hex}/{filename}"

    async def generate_image(self, *, prompt: str, reference_urls: list[str], request_id: str, metadata: dict[str, Any] | None = None) -> ProviderResult:
        return ProviderResult(
            "success",
            "https://placehold.co/720x1280/png?text=Hook+Studio",
            f"fake-image-{request_id}",
            trace={"provider": "fake", "attempts": 1},
        )

    async def submit_video(self, *, prompt: str, image_urls: list[str], duration: int, request_id: str, video_urls: list[str] | None = None, metadata: dict[str, Any] | None = None, generation_mode: str = "multimodal") -> ProviderResult:
        return ProviderResult(
            "success",
            "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
            f"fake-video-{request_id}",
            trace={"provider": "fake", "attempts": 1, "generation_mode": generation_mode},
        )

    async def poll_video(self, submit_id: str, *, request_id: str, external_ref: str = "hook-studio") -> ProviderResult:
        return ProviderResult("success", "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4", submit_id)

    async def cancel_video(self, submit_id: str, *, request_id: str) -> bool:
        return True

    async def probe_media(self, source_uri: str, *, request_id: str | None = None) -> dict[str, Any]:
        return {
            "duration": 5.0,
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }

    async def understand(self, *, text: str, image_urls: list[str] | None = None, video_urls: list[str] | None = None, request_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"summary": "测试生产计划", "shots": []}

    async def transcode(self, source_uris: list[str], *, filename: str = "transcoded.mp4", request_id: str | None = None, metadata: dict[str, Any] | None = None) -> ProviderResult:
        return ProviderResult("success", "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4", trace={"source_count": len(source_uris)})

    async def extract_frame(self, source_uri: str, *, offset_from_end: float = 0.5, filename: str = "frame.jpg", request_id: str | None = None, metadata: dict[str, Any] | None = None) -> ProviderResult:
        return ProviderResult("success", "https://placehold.co/720x1280/jpg?text=Frame")
