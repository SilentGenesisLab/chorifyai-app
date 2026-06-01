# -*- coding: UTF-8 -*-
"""
ElevenLabs TTS / 音乐生成封装。

公开:
    synthesize_speech(text, voice_id=..., ...) -> dict
        文本 -> mp3 -> OSS, 返回 {audio_url, voice_id, model_id, bytes}
    generate_music(prompt, music_length_ms=..., ...) -> dict
        音乐提示 -> mp3 -> OSS, 返回 {audio_url, music_length_ms, model_id, bytes}
    list_voices() -> dict
        透传 ElevenLabs /v1/voices

环境变量 (.env):
    ELEVENLABS_API_KEY        必填
    ELEVENLABS_TTS_MODEL      可选, 默认 eleven_multilingual_v2
    ELEVENLABS_MUSIC_MODEL    可选, 默认 music_v1
    ELEVENLABS_DEFAULT_VOICE  可选, 默认 EST9Ui6982FZPSi7gCHi
                              (切换音色: 去 https://elevenlabs.io/app/developers 找)
"""

import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

# 关掉代理 (跟 doubao.py 一致, 避免本机 7888 代理把 api.elevenlabs.io 也拦了)
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_no_proxy_opener)

# 加载 .env
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

_BASE_URL = "https://api.elevenlabs.io"
_DEFAULT_TTS_MODEL = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
_DEFAULT_MUSIC_MODEL = os.environ.get("ELEVENLABS_MUSIC_MODEL", "music_v1")
_DEFAULT_VOICE_ID = os.environ.get("ELEVENLABS_DEFAULT_VOICE", "EST9Ui6982FZPSi7gCHi")

_VALID_TTS_FORMATS = {
    "mp3_44100_128", "mp3_44100_64", "mp3_22050_32",
    "pcm_16000", "pcm_22050", "pcm_44100",
}
_VALID_MUSIC_FORMATS = {"mp3_44100_128", "mp3_44100_64"}


# 延迟导入, 让没装 oss2 的纯单测也能跑业务函数 (返回时 audio_url 会是 None)
def _try_upload_to_oss(local_path: Path, prefix: str) -> Optional[str]:
    try:
        import sys as _sys
        _proj_root = Path(__file__).resolve().parents[2]
        if str(_proj_root) not in _sys.path:
            _sys.path.insert(0, str(_proj_root))
        from oss_util import upload_file  # type: ignore
        return upload_file(local_path, prefix=prefix)
    except Exception as e:
        print(f"[elevenlabs] OSS 上传失败, 退回本地路径: {type(e).__name__}: {e}")
        return None


def _api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("缺少 ELEVENLABS_API_KEY, 请在 .env 配置")
    return key


def _post_binary(url: str, payload: dict, timeout: float) -> bytes:
    """POST JSON, 期望返回 audio/mpeg 二进制。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": _api_key(),
            "accept": "audio/mpeg",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {err_body}") from e


def _ext_from_format(output_format: str) -> str:
    if output_format.startswith("mp3"):
        return ".mp3"
    if output_format.startswith("pcm"):
        return ".pcm"
    return ".bin"


def synthesize_speech(
    text: str,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True,
    output_format: str = "mp3_44100_128",
    upload: bool = True,
    oss_prefix: str = "chorify-video/tts",
) -> dict:
    """
    文本转语音 -> 落本地临时文件 -> 上传 OSS -> 返回 URL + 元数据。

    :param text: 文本 (1-5000 字)
    :param voice_id: ElevenLabs voice id, 默认 Rachel
    :param model_id: TTS 模型, 默认 eleven_multilingual_v2 (支持中/泰/英)
    :param stability: 0-1, 越高越平稳
    :param similarity_boost: 0-1, 越高越像参考音色
    :param style: 0-1, v2 模型情感强度
    :param use_speaker_boost: 是否加强音色
    :param output_format: mp3_44100_128 / mp3_44100_64 / mp3_22050_32 / pcm_*
    :param upload: 是否上传 OSS, False 时只落本地
    :param oss_prefix: OSS key 前缀
    :return: {"audio_url", "local_path", "voice_id", "model_id", "bytes", "duration_ms"}
    """
    if not text or not text.strip():
        raise ValueError("text 不能为空")
    if len(text) > 5000:
        raise ValueError(f"text 过长 ({len(text)} 字), 上限 5000")
    if output_format not in _VALID_TTS_FORMATS:
        raise ValueError(f"output_format 不合法: {output_format}, 可选 {sorted(_VALID_TTS_FORMATS)}")

    voice_id = voice_id or _DEFAULT_VOICE_ID
    model_id = model_id or _DEFAULT_TTS_MODEL

    url = f"{_BASE_URL}/v1/text-to-speech/{urllib.parse.quote(voice_id)}"
    url += "?" + urllib.parse.urlencode({"output_format": output_format})

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": use_speaker_boost,
        },
    }

    t0 = time.time()
    audio = _post_binary(url, payload, timeout=120.0)
    cost_ms = int((time.time() - t0) * 1000)

    ext = _ext_from_format(output_format)
    tmp = tempfile.NamedTemporaryFile(
        prefix="el_tts_", suffix=ext, delete=False,
    )
    tmp.write(audio)
    tmp.close()
    local_path = Path(tmp.name)

    audio_url = _try_upload_to_oss(local_path, oss_prefix) if upload else None

    return {
        "audio_url": audio_url,
        "local_path": str(local_path) if not audio_url else None,
        "voice_id": voice_id,
        "model_id": model_id,
        "bytes": len(audio),
        "cost_ms": cost_ms,
        "output_format": output_format,
    }


def generate_music(
    prompt: str,
    music_length_ms: int = 30000,
    model_id: Optional[str] = None,
    output_format: str = "mp3_44100_128",
    upload: bool = True,
    oss_prefix: str = "chorify-video/music",
) -> dict:
    """
    文本提示生成音乐 -> 落本地临时文件 -> 上传 OSS -> 返回 URL + 元数据。

    :param prompt: 音乐描述, 英文效果更佳 (e.g. "upbeat lofi hip hop with rain")
    :param music_length_ms: 10000-300000, 即 10-300 秒
    :param model_id: 默认 music_v1
    :param output_format: mp3_44100_128 / mp3_44100_64
    :param upload: 是否上传 OSS
    :param oss_prefix: OSS key 前缀
    :return: {"audio_url", "local_path", "music_length_ms", "model_id", "bytes", "cost_ms"}
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt 不能为空")
    if not (10_000 <= music_length_ms <= 300_000):
        raise ValueError(f"music_length_ms 超范围: {music_length_ms}, 需在 10000-300000")
    if output_format not in _VALID_MUSIC_FORMATS:
        raise ValueError(f"output_format 不合法: {output_format}, 可选 {sorted(_VALID_MUSIC_FORMATS)}")

    model_id = model_id or _DEFAULT_MUSIC_MODEL

    url = f"{_BASE_URL}/v1/music"
    url += "?" + urllib.parse.urlencode({"output_format": output_format})

    payload = {
        "prompt": prompt,
        "music_length_ms": music_length_ms,
        "model_id": model_id,
    }

    t0 = time.time()
    audio = _post_binary(url, payload, timeout=300.0)
    cost_ms = int((time.time() - t0) * 1000)

    tmp = tempfile.NamedTemporaryFile(
        prefix="el_music_", suffix=".mp3", delete=False,
    )
    tmp.write(audio)
    tmp.close()
    local_path = Path(tmp.name)

    audio_url = _try_upload_to_oss(local_path, oss_prefix) if upload else None

    return {
        "audio_url": audio_url,
        "local_path": str(local_path) if not audio_url else None,
        "music_length_ms": music_length_ms,
        "model_id": model_id,
        "bytes": len(audio),
        "cost_ms": cost_ms,
        "output_format": output_format,
    }


def list_voices() -> dict:
    """透传 GET /v1/voices, 返回原始 JSON。"""
    req = urllib.request.Request(
        f"{_BASE_URL}/v1/voices",
        headers={"xi-api-key": _api_key(), "accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {err_body}") from e
