from __future__ import annotations

import asyncio
import inspect
import mimetypes
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterable, BinaryIO, Iterable
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

    @staticmethod
    def _rewind_files(kwargs: dict[str, Any]) -> None:
        for value in (kwargs.get("files") or {}).values():
            file_value = value[1] if isinstance(value, tuple) and len(value) > 1 else value
            seek = getattr(file_value, "seek", None)
            if callable(seek):
                seek(0)

    async def _request(self, method: str, path: str, *, attempts: int = 2, request_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owned = self._client is None
        last: Exception | None = None
        try:
            for attempt in range(attempts):
                try:
                    self._rewind_files(kwargs)
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

    @staticmethod
    async def _spool_content(
        content: bytes | bytearray | memoryview | BinaryIO | Iterable[bytes] | AsyncIterable[bytes],
        *,
        max_bytes: int,
    ) -> tuple[tempfile.SpooledTemporaryFile[bytes], int]:
        if max_bytes <= 0:
            raise ProviderRejected("附件大小上限必须大于0")
        spool = tempfile.SpooledTemporaryFile(max_size=min(max_bytes, 2 * 1024 * 1024), mode="w+b")
        size = 0

        def write_chunk(chunk: bytes | bytearray | memoryview) -> None:
            nonlocal size
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise ProviderRejected("附件流必须返回bytes")
            size += len(chunk)
            if size > max_bytes:
                raise ProviderRejected(f"附件不能超过{max_bytes // (1024 * 1024) or 1}MB")
            spool.write(chunk)

        try:
            if isinstance(content, (bytes, bytearray, memoryview)):
                write_chunk(content)
            elif hasattr(content, "read"):
                while True:
                    chunk = content.read(1024 * 1024)  # type: ignore[union-attr]
                    if inspect.isawaitable(chunk):
                        chunk = await chunk
                    if not chunk:
                        break
                    write_chunk(chunk)
            elif hasattr(content, "__aiter__"):
                async for chunk in content:  # type: ignore[union-attr]
                    write_chunk(chunk)
            else:
                for chunk in content:  # type: ignore[union-attr]
                    write_chunk(chunk)
            if size == 0:
                raise ProviderRejected("附件内容为空")
            spool.seek(0)
            return spool, size
        except Exception:
            spool.close()
            raise

    async def upload_attachment(
        self,
        filename: str,
        content: bytes | bytearray | memoryview | BinaryIO | Iterable[bytes] | AsyncIterable[bytes],
        content_type: str | None = None,
        *,
        stage: str = "attachment.upload",
        request_id: str | None = None,
        max_bytes: int = 512 * 1024 * 1024,
    ) -> str:
        """Upload a bounded attachment without loading large media entirely into memory."""

        safe_name = Path(filename).name.strip()
        if not safe_name or safe_name in {".", ".."} or "\x00" in safe_name:
            raise ProviderRejected("附件文件名无效")
        resolved_type = (content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream").split(";", 1)[0].strip().lower()
        spool, _ = await self._spool_content(content, max_bytes=max_bytes)
        try:
            data = await self._request(
                "POST",
                "/capabilities/v1/storage/upload",
                request_id=request_id,
                files={"file": (safe_name, spool, resolved_type)},
                data={"external_ref": f"hook-studio:{request_id}" if request_id else "hook-studio", "stage": stage},
            )
        finally:
            spool.close()
        uri = data.get("uri")
        if not uri:
            raise ProviderRejected("Kernel上传响应缺少uri")
        return str(uri)

    async def upload_reference(self, filename: str, content: bytes, content_type: str, *, request_id: str | None = None) -> str:
        if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise ProviderRejected("参考图格式仅支持 JPEG/PNG/WebP/GIF")
        if len(content) > 10 * 1024 * 1024:
            raise ProviderRejected("参考图不能超过10MB")
        return await self.upload_attachment(
            filename,
            content,
            content_type,
            stage="reference.upload",
            request_id=request_id,
            max_bytes=10 * 1024 * 1024,
        )

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

    async def submit_video(
        self,
        *,
        prompt: str,
        image_urls: list[str],
        duration: int,
        request_id: str,
        video_urls: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        payload = {"prompt": prompt, "image_urls": image_urls, "video_urls": list(video_urls or []), "duration": duration, "ratio": "9:16", "resolution": "720p", "external_ref": f"hook-studio:{request_id}", "stage": "video.submit", "metadata": {"hook_job_id": request_id, **(metadata or {})}}
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

    async def understand(
        self,
        *,
        text: str,
        image_urls: list[str] | None = None,
        video_urls: list[str] | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rid = request_id or f"understand-{uuid4().hex}"
        payload = {
            "text": text,
            "image_urls": list(image_urls or []),
            "video_urls": list(video_urls or []),
            "external_ref": f"hook-studio:{rid}",
            "stage": "understand.evaluate",
            "metadata": {"hook_job_id": rid, **(metadata or {})},
        }
        data = await self._request("POST", "/capabilities/v1/understand/evaluate", json=payload, request_id=rid)
        analysis = data.get("analysis")
        if not isinstance(analysis, dict):
            raise ProviderRejected("理解响应缺少analysis")
        return analysis

    async def transcode(
        self,
        source_uris: list[str],
        *,
        filename: str = "transcoded.mp4",
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if not source_uris:
            raise ProviderRejected("转码至少需要一个源媒体")
        rid = request_id or f"transcode-{uuid4().hex}"
        payload = {
            "source_uris": source_uris,
            "filename": Path(filename).name or "transcoded.mp4",
            "external_ref": f"hook-studio:{rid}",
            "stage": "media.transcode",
            "metadata": {"hook_job_id": rid, **(metadata or {})},
        }
        data = await self._request("POST", "/capabilities/v1/media/transcode", json=payload, request_id=rid)
        url = data.get("video_url")
        if not url:
            raise ProviderRejected("转码响应缺少video_url")
        return ProviderResult("success", str(url), local_path=data.get("local_path"), trace={"source_count": data.get("source_count", len(source_uris))})

    async def extract_frame(
        self,
        source_uri: str,
        *,
        offset_from_end: float = 0.5,
        filename: str = "frame.jpg",
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        rid = request_id or f"frame-{uuid4().hex}"
        payload = {
            "source_uri": source_uri,
            "offset_from_end": offset_from_end,
            "filename": Path(filename).name or "frame.jpg",
            "external_ref": f"hook-studio:{rid}",
            "stage": "media.extract_frame",
            "metadata": {"hook_job_id": rid, **(metadata or {})},
        }
        data = await self._request("POST", "/capabilities/v1/media/extract-frame", json=payload, request_id=rid)
        url = data.get("frame_url")
        if not url:
            raise ProviderRejected("抽帧响应缺少frame_url")
        return ProviderResult("success", str(url), local_path=data.get("local_path"))
