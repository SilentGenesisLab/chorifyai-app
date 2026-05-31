"""AI 语音 — 豆包(字节)音色查询 + TTS 合成(→OSS) + ASR 识别
            + AI 写文案 / 翻译(火山方舟豆包大模型) + 语音克隆(VoxCPM)。

所有 AI 能力都在后端封装，前端只调本路由，密钥不下发：
- 音色表来自 app/data/voices.json（由 scripts/build_voices.py 从 Excel 生成）
- TTS 流式 NDJSON，base64 分片拼接后上传 OSS 返回公网 URL
- ASR 接收公网音频 URL（如本平台 OSS），返回识别文本
- /write   提示词 -> 豆包大模型生成配音文案
- /translate  音频或文本 -> ASR/翻译，可选用所选音色合成译文音频
- /clone   参考音 + 文本 -> VoxCPM 克隆音色 -> OSS 音频 URL
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
from app.services import ark, voxcpm
from app.services.oss import put_object

router = APIRouter(prefix="/api/voice", tags=["voice"])

# Connect direct to ByteDance (domestic) — ignore any HTTP(S)_PROXY env var,
# which (e.g. a local VPN proxy) would corrupt the streamed TTS response.
_session = requests.Session()
_session.trust_env = False

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


# ----------------------------------------------------------------------------
# 内部 helper：TTS 合成 / ASR 识别 / 音频上传（供多个端点复用）
# ----------------------------------------------------------------------------
def _tts_bytes(
    text: str,
    speaker: str,
    fmt: str = "mp3",
    sample_rate: int = 24000,
    uid: str = "chorify",
) -> bytes:
    """调豆包 TTS，拼接流式分片，返回完整音频二进制。失败抛 HTTPException。"""
    headers = {
        "X-Api-Access-Key": settings.doubao_tts_access_key,
        "X-Api-Resource-Id": settings.doubao_tts_resource_id,
        "X-Api-App-Id": settings.doubao_tts_app_id,
        "Content-Type": "application/json",
    }
    body = {
        "user": {"uid": uid},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": fmt,
                "sample_rate": sample_rate,
                "enable_timestamp": True,
            },
        },
    }
    try:
        r = _session.post(
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
    nlines = 0
    for raw in r.iter_lines():
        if not raw:
            continue
        nlines += 1
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        code = obj.get("code")
        if code not in (0, None):
            err = obj.get("message") or f"code {code}"
        d = obj.get("data")
        if isinstance(d, str) and d:
            try:
                audio += base64.b64decode(d)
            except Exception:
                pass

    if not audio:
        raise HTTPException(
            status_code=502,
            detail=f"TTS 无音频返回: {err or '未知'} (lines={nlines})",
        )
    return bytes(audio)


def _asr_text(url: str, model_name: str = "bigmodel", uid: str = "chorify") -> tuple[str, float | None]:
    """调豆包 ASR，返回 (识别文本, 时长秒)。失败抛 HTTPException。"""
    headers = {
        "X-Api-Key": settings.doubao_asr_api_key,
        "X-Api-Resource-Id": settings.doubao_asr_resource_id,
        "X-Api-Sequence": "-1",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    body = {
        "user": {"uid": uid},
        "audio": {"url": url},
        "request": {"model_name": model_name},
    }
    try:
        r = _session.post(settings.doubao_asr_url, headers=headers, json=body, timeout=90)
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
    return text, duration


def _put_audio(audio: bytes, fmt: str, prefix: str = "tts") -> tuple[str, str]:
    """音频二进制上传 OSS，返回 (公网 url, key)。"""
    if settings.oss_provider != "aliyun":
        raise HTTPException(status_code=500, detail="OSS 未配置，无法返回可播放链接")
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"{prefix}/{day}/{uuid.uuid4().hex}.{fmt}"
    content_type = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"
    url = put_object(key, audio, content_type)
    return url, key


# ----------------------------------------------------------------------------
# 音色 / 供应商
# ----------------------------------------------------------------------------
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


@router.get("/languages")
def languages() -> dict:
    """翻译 / 识别支持的语言列表。"""
    return {"ok": True, "languages": ark.LANGUAGES}


# ----------------------------------------------------------------------------
# TTS：文字转语音
# ----------------------------------------------------------------------------
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

    audio = _tts_bytes(req.text, req.speaker, req.format, req.sample_rate, req.uid)
    url, key = _put_audio(audio, req.format, prefix="tts")
    return {
        "ok": True,
        "url": url,
        "key": key,
        "bytes": len(audio),
        "provider": req.provider,
        "speaker": req.speaker,
    }


# ----------------------------------------------------------------------------
# ASR：语音转文字
# ----------------------------------------------------------------------------
class ASRRequest(BaseModel):
    url: str
    model_name: str = "bigmodel"
    uid: str = "chorify"


@router.post("/asr")
def asr(req: ASRRequest) -> dict:
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="缺少音频 url")
    text, duration = _asr_text(req.url, req.model_name, req.uid)
    return {"ok": True, "text": text, "duration": duration}


# ----------------------------------------------------------------------------
# AI 写文案：提示词 -> 豆包大模型 -> 配音文案
# ----------------------------------------------------------------------------
class WriteRequest(BaseModel):
    prompt: str
    max_chars: int = 200


@router.post("/write")
def write(req: WriteRequest) -> dict:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="请输入提示词")
    limit = max(20, min(req.max_chars, 500))
    system = (
        "你是资深短视频 / 广告配音文案写手。根据用户给的主题或需求，"
        "写一段适合口播配音的中文文案：自然口语化、有节奏、有感染力。"
        "直接输出文案正文，不要解释、不要标题、不要分点、不要加引号。"
        f"长度控制在 {limit} 字以内。"
    )
    try:
        text = ark.complete_text(req.prompt.strip(), system=system)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True, "text": text}


# ----------------------------------------------------------------------------
# 翻译：音频/文本 -> ASR/翻译 -> 可选合成译文音频
# ----------------------------------------------------------------------------
class TranslateRequest(BaseModel):
    text: str | None = None
    audio_url: str | None = None
    source: str = "auto"
    target: str = "zh"
    # 若给 speaker，则把译文用该音色合成为音频，返回 url
    speaker: str | None = None
    format: str = "mp3"
    uid: str = "chorify"


@router.post("/translate")
def translate(req: TranslateRequest) -> dict:
    source_text = (req.text or "").strip()
    duration = None
    if not source_text:
        if not (req.audio_url or "").strip():
            raise HTTPException(status_code=400, detail="请提供待翻译文本或音频")
        source_text, duration = _asr_text(req.audio_url, uid=req.uid)
    if not source_text:
        raise HTTPException(status_code=400, detail="未能获得可翻译的文本")

    try:
        translated = ark.translate_text(source_text, req.source, req.target)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    url = key = None
    if req.speaker and req.speaker.strip() and translated.strip():
        audio = _tts_bytes(translated, req.speaker, req.format, uid=req.uid)
        url, key = _put_audio(audio, req.format, prefix="tts")

    return {
        "ok": True,
        "sourceText": source_text,
        "text": translated,
        "duration": duration,
        "url": url,
        "key": key,
        "target": req.target,
    }


# ----------------------------------------------------------------------------
# 语音克隆：参考音 + 文本 -> VoxCPM -> OSS 音频 URL
# ----------------------------------------------------------------------------
class CloneRequest(BaseModel):
    text: str
    reference_url: str
    # 终极克隆（深度还原）：提供参考音的精确转写，相似度更高
    ultimate: bool = False
    prompt_text: str | None = None
    cfg_value: float = 2.0
    inference_timesteps: int = 10
    uid: str = "chorify"


@router.get("/clone/health")
def clone_health() -> dict:
    return {"ok": True, **voxcpm.health()}


@router.post("/clone")
def clone(req: CloneRequest) -> dict:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="请输入要克隆的目标文本")
    if not (req.reference_url or "").strip():
        raise HTTPException(status_code=400, detail="请上传参考音色")
    if not voxcpm.available():
        raise HTTPException(status_code=503, detail="语音克隆服务未配置（VOXCPM_URL）")

    prompt_text = None
    if req.ultimate:
        prompt_text = (req.prompt_text or "").strip()
        if not prompt_text:
            raise HTTPException(
                status_code=400, detail="终极克隆需要参考音的精确文本转写"
            )

    try:
        wav = voxcpm.clone(
            req.text.strip(),
            req.reference_url.strip(),
            prompt_text=prompt_text,
            cfg_value=req.cfg_value,
            inference_timesteps=req.inference_timesteps,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    url, key = _put_audio(wav, "wav", prefix="clone")
    return {"ok": True, "url": url, "key": key, "bytes": len(wav)}
