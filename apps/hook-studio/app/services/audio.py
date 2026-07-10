from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from app.services.media_ops import replace_audio_file


class AudioServiceError(RuntimeError):
    code = "AUDIO_REPLACEMENT_FAILED"


class AudioReplacementService:
    def __init__(self, provider: Any, *, base_url: str, api_key: str | None, default_voice: str):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_voice = default_voice

    async def synthesize(self, text: str, *, voice_id: str | None = None) -> str:
        if not self.api_key:
            raise AudioServiceError("声音服务尚未配置")
        payload = {"engine": "volcano", "text": text, "voice_id": voice_id or self.default_voice, "sample_rate": 24000, "enable_timestamp": False, "upload": True}
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.base_url}/v1/tts/speech", headers={"X-Internal-Key": self.api_key}, json=payload)
            response.raise_for_status(); data = response.json()
        url = data.get("audio_url") or data.get("url")
        if not url:
            raise AudioServiceError("声音服务未返回音频地址")
        return str(url)

    async def replace(self, source_video_url: str, text: str, *, voice_id: str | None = None, request_id: str | None = None) -> dict[str, Any]:
        audio_url = await self.synthesize(text, voice_id=voice_id)
        output = await replace_audio_file(source_video_url, audio_url)
        rid = request_id or uuid4().hex
        result_url = await self.provider.upload_blob(f"voice-replaced-{rid}.mp4", output, "video/mp4", stage="audio.replace", request_id=rid)
        probe = await self.provider.probe_media(result_url, request_id=f"probe-{rid}")
        streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
        if not any(item.get("codec_type") == "audio" for item in streams):
            raise AudioServiceError("换声结果缺少音轨")
        return {"result_url": result_url, "audio_url": audio_url, "probe": probe}

