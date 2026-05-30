"""AI 语音 — 豆包(字节)音色查询 + TTS 合成(→OSS) + ASR 识别.

- 音色表来自 app/data/voices.json（由 scripts/build_voices.py 从 Excel 生成）
- TTS 流式返回 NDJSON，每行 data 为 base64 音频分片，拼接后上传 OSS 返回公网 URL
- ASR 接收音频 URL（公网可访问，例如本平台 OSS），返回识别文本
"""
import base64
import json
import os
import uuid
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.oss import put_object

router = APIRouter(prefix="/api/voice", tags=["voice"])

_DATA = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "voices.json"
)

# 当前已接入 + 规划中的语音供应商（前端据此标明"目前豆包，后续扩展"）
PROVIDERS = [
    {"id": "doubao", "label": "豆包", "enabled": True},
    {"id": "minimax", "label": "MiniMax", "enabled": False, "note": "即将支持"},
    {"id": "elevenlabs", "label": "ElevenLabs", "enabled": False, "note": "即将支持"},
]


def _load_voices() -> dict:
    with open(_DATA, encoding="utf-8") as f:
        return json.load(f)


@router.get("/providers")
def providers() -> dict:
    data = _load_voices()
    out = []
    for p in PROVIDERS:
        item = dict(p)
        item["count"] = data.get("count", 0) if p["id"] == "doubao" else 0
        out.append(item)
    return {"ok": True, "providers": out}


@router.get("/voices")
def voices(provider: str = "doubao") -> dict:
    if provider != "doubao":
        return {"ok": True, "provider": provider, "count": 0, "voices": []}
    return {"ok": True, **_load_voices()}


class TTSRequest(BaseModel):
    text: str
    speaker: str
    provider: str = "doubao"
    format: str = "mp3"
    sample_rate: int = 24000
    emotion: str | None = None
    uid: str = "chorify"


@router.post("/tts")
def tts(req: TTSRequest) -> dict:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="配音文本不能为空")
    if not req.speaker.strip():
        raise HTTPException(status_code=400, detail="请选择音色")
    if settings.oss_provider != "aliyun":
        raise HTTPException(status_code=500, detail="OSS 未配置，无法返回可播放链接")

    headers = {
        "X-Api-Access-Key": settings.doubao_tts_access_key,
        "X-Api-Resource-Id": settings.doubao_tts_resource_id,
        "X-Api-App-Id": settings.doubao_tts_app_id,
        "Content-Type": "application/json",
    }
    body = {
        "user": {"uid": req.uid},
        "req_params": {
            "text": req.text,
            "speaker": req.speaker,
            "audio_params": {
                "format": req.format,
                "sample_rate": req.sample_rate,
                "enable_timestamp": True,
            },
        },
    }

    try:
        r = requests.post(
            settings.doubao_tts_url, headers=headers, json=body, stream=True, timeout=120
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"TTS 请求失败: {e}")

    if r.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"TTS 失败 HTTP {r.status_code}: {r.text[:200]}"
        )

    audio = bytearray()
    err: str | None = None
    for raw in r.iter_lines():
        if not raw:
            continue
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        code = obj.get("code")
        if code not in (0, None):
            err = obj.get("message") or f"code {code}"
        d = obj.get("data")
        if d:
            try:
                audio += base64.b64decode(d)
            except Exception:
                pass

    if not audio:
        raise HTTPException(status_code=502, detail=f"TTS 无音频返回: {err or '未知错误'}")

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"tts/{day}/{uuid.uuid4().hex}.{req.format}"
    content_type = "audio/mpeg" if req.format == "mp3" else f"audio/{req.format}"
    url = put_object(key, bytes(audio), content_type)

    return {
        "ok": True,
        "url": url,
        "key": key,
        "bytes": len(audio),
        "provider": req.provider,
        "speaker": req.speaker,
    }


class ASRRequest(BaseModel):
    url: str
    model_name: str = "bigmodel"
    uid: str = "chorify"


@router.post("/asr")
def asr(req: ASRRequest) -> dict:
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="缺少音频 url")

    headers = {
        "X-Api-Key": settings.doubao_asr_api_key,
        "X-Api-Resource-Id": settings.doubao_asr_resource_id,
        "X-Api-Sequence": "-1",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    body = {
        "user": {"uid": req.uid},
        "audio": {"url": req.url},
        "request": {"model_name": req.model_name},
    }

    try:
        r = requests.post(settings.doubao_asr_url, headers=headers, json=body, timeout=90)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"ASR 请求失败: {e}")

    if r.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"ASR 失败 HTTP {r.status_code}: {r.text[:200]}"
        )

    data = r.json()
    result = data.get("result") or {}
    text = result.get("text", "")
    duration = (data.get("audio_info") or {}).get("duration")
    return {"ok": True, "text": text, "duration": duration}
