from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx


class ProviderError(RuntimeError):
    code = "PROVIDER_REJECTED"


class ProviderTimeout(ProviderError):
    code = "PROVIDER_TIMEOUT"


class ProviderRejected(ProviderError):
    code = "PROVIDER_REJECTED"


@dataclass(frozen=True)
class ProviderResult:
    status: str
    result_url: str | None = None
    submit_id: str | None = None
    local_path: str | None = None
    failure_reason: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)


class KernelProvider:
    """Server-only adapter for the verified Kernel capability contract."""

    def __init__(self, base_url: str, api_key: str | None, *, timeout_seconds: float = 60, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client

    def _headers(self, request_id: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if request_id:
            headers["Idempotency-Key"] = request_id
            headers["X-Request-ID"] = request_id
        return headers

    async def _request(self, method: str, path: str, *, attempts: int = 2, request_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owned = self._client is None
        last: Exception | None = None
        try:
            for attempt in range(attempts):
                try:
                    response = await client.request(method, f"{self.base_url}{path}", headers=self._headers(request_id), **kwargs)
                    if response.status_code >= 500 and attempt + 1 < attempts:
                        await asyncio.sleep(0.15 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ProviderRejected("Kernel返回了无效JSON对象")
                    data["_hook_attempts"] = attempt + 1
                    return data
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last = exc
                    if attempt + 1 >= attempts:
                        raise ProviderTimeout(f"Kernel请求超时，已尝试{attempts}次") from exc
                    await asyncio.sleep(0.15 * (attempt + 1))
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text[:500]
                    raise ProviderRejected(f"Kernel拒绝请求({exc.response.status_code}): {body}") from exc
            raise ProviderTimeout("Kernel请求超时") from last
        finally:
            if owned:
                await client.aclose()

    async def upload_reference(self, filename: str, content: bytes, content_type: str, *, request_id: str | None = None) -> str:
        if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise ProviderRejected("参考图格式仅支持 JPEG/PNG/WebP/GIF")
        if len(content) > 10 * 1024 * 1024:
            raise ProviderRejected("参考图不能超过10MB")
        data = await self._request("POST", "/capabilities/v1/storage/upload", request_id=request_id, files={"file": (filename, content, content_type)}, data={"external_ref": "hook-studio", "stage": "reference.upload"})
        uri = data.get("uri")
        if not uri:
            raise ProviderRejected("Kernel上传响应缺少uri")
        return str(uri)

    async def upload_blob(self, filename: str, content: bytes, content_type: str, *, stage: str, request_id: str | None = None) -> str:
        data = await self._request(
            "POST", "/capabilities/v1/storage/upload", request_id=request_id,
            files={"file": (filename, content, content_type)},
            data={"external_ref": "hook-studio", "stage": stage},
        )
        uri = data.get("uri")
        if not uri:
            raise ProviderRejected("Kernel上传响应缺少uri")
        return str(uri)

    async def generate_image(self, *, prompt: str, reference_urls: list[str], request_id: str, metadata: dict[str, Any] | None = None) -> ProviderResult:
        payload = {"prompt": prompt, "reference_urls": reference_urls, "aspect_ratio": "9:16", "external_ref": f"hook-studio:{request_id}", "stage": "image.generate", "metadata": {"hook_job_id": request_id, **(metadata or {})}}
        data = await self._request("POST", "/capabilities/v1/images/generate", json=payload, request_id=request_id)
        url = data.get("image_url")
        if not url:
            raise ProviderRejected("图片生成响应缺少image_url")
        trace = dict(data.get("provider_trace") or {})
        trace["attempts"] = int(data.get("_hook_attempts", 1))
        return ProviderResult("success", str(url), trace.get("submit_id"), data.get("local_path"), trace=trace)

    async def submit_video(self, *, prompt: str, image_urls: list[str], duration: int, request_id: str, metadata: dict[str, Any] | None = None) -> ProviderResult:
        payload = {"prompt": prompt, "image_urls": image_urls, "video_urls": [], "duration": duration, "ratio": "9:16", "resolution": "720p", "external_ref": f"hook-studio:{request_id}", "stage": "video.submit", "metadata": {"hook_job_id": request_id, **(metadata or {})}}
        data = await self._request("POST", "/capabilities/v1/videos/generate", json=payload, request_id=request_id)
        submit_id = data.get("submit_id")
        if not submit_id:
            raise ProviderRejected("视频提交响应缺少submit_id")
        trace = dict(data.get("provider_trace") or {})
        trace["attempts"] = int(data.get("_hook_attempts", 1))
        return ProviderResult(str(data.get("status", "submitted")), data.get("video_url"), str(submit_id), data.get("local_path"), data.get("failure_reason"), trace)

    async def poll_video(self, submit_id: str, *, request_id: str, external_ref: str = "hook-studio") -> ProviderResult:
        data = await self._request("GET", f"/capabilities/v1/videos/jobs/{submit_id}", params={"external_ref": f"{external_ref}:{request_id}", "stage": "video.poll"}, request_id=request_id)
        trace = dict(data.get("raw") or {})
        trace["poll_attempts"] = int(data.get("_hook_attempts", 1))
        return ProviderResult(str(data.get("status", "running")), data.get("video_url"), str(data.get("submit_id") or submit_id), data.get("local_path"), data.get("failure_reason"), trace)

    async def cancel_video(self, submit_id: str, *, request_id: str) -> bool:
        data = await self._request("POST", f"/capabilities/v1/videos/jobs/{submit_id}/cancel", params={"external_ref": f"hook-studio:{request_id}"}, request_id=request_id)
        return bool(data.get("cancelled"))

    async def probe_media(self, source_uri: str, *, request_id: str | None = None) -> dict[str, Any]:
        rid = request_id or f"probe-{uuid4().hex}"
        data = await self._request("POST", "/capabilities/v1/media/probe", json={"source_uri": source_uri, "external_ref": f"hook-studio:{rid}", "stage": "video.postflight", "metadata": {"hook_job_id": rid}}, request_id=rid)
        probe = data.get("probe")
        if not isinstance(probe, dict):
            raise ProviderRejected("媒体探测响应缺少probe")
        return probe
