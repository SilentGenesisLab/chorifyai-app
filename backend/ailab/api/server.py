# -*- coding: UTF-8 -*-
"""
ASR / 翻译 HTTP 服务 (FastAPI)

启动:
    python -m ailab.api.server                 # 默认 0.0.0.0:8089
    python -m ailab.api.server --port 9000
    uvicorn ailab.api.server:app --host 0.0.0.0 --port 8089

接口:
    GET  /                                      根, 同 /health
    GET  /health                                心跳
    GET  /docs                                  Swagger UI (FastAPI 自带)
    POST /asr/audio       识别音频 (URL/本地)
    POST /asr/video       识别视频 (抽音频后识别)
    POST /asr/extract     抽音频上传 OSS
    POST /asr/translate   一站式: 视频 -> ASR -> 翻译
    POST /tts/speech              ElevenLabs 文本转语音 -> mp3 -> OSS
    POST /tts/music               ElevenLabs 文本生成音乐 -> mp3 -> OSS
    GET  /tts/voices              列出 ElevenLabs 可用音色
    POST /tts/voxcpm              VoxCPM2 文本转语音 / Voice Design (wav)
    POST /tts/voxcpm/clone        VoxCPM2 上传参考音色克隆 (multipart, wav)
    POST /tts/voxcpm/clone_path   VoxCPM2 本地路径克隆 (含终极克隆, wav)
    GET  /tts/voxcpm/health       VoxCPM2 后端心跳

公共 body 字段:
    url 或 path       二选一 (url 公网链接, path 服务器本地路径)
    language          可选, 'thai' / 'zh' / 'en' 等
其他字段见各接口文档 (curl 示例见同目录 README.md)。

返回:
    {"code": 0, "msg": "ok", "data": {...}}
    {"code": -1, "msg": "<error>", "data": null}
"""

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

import httpx

# Windows 控制台 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

# 项目根入 sys.path (便于 -m 与 uvicorn 启动都能 import 到 ailab)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, model_validator

from ailab.asr import (
    extract_audio_to_oss,
    transcribe_and_translate,
    transcribe_audio,
    transcribe_video,
)
from ailab.tts import (
    generate_music,
    list_voices as tts_list_voices,
    synthesize_speech,
)


app = FastAPI(
    title="ASR & Translate Service",
    description=(
        "基于 OpenAI Whisper + 豆包翻译的语音识别 / 翻译 / 音轨提取服务。\n\n"
        "**通用约定**:\n"
        "- 所有 POST 端点的 body 都需要 `url` 或 `path` 其中之一 (二选一)\n"
        "- `url` = 公网音视频地址 (会自动下载到服务器临时文件后处理)\n"
        "- `path` = 服务器本地文件路径 (无需下载, 适合大文件)\n"
        "- 统一返回格式: `{code: 0|‑1, msg: 'ok'|err, data: {...}|null}`\n"
        "- 默认引擎 `faster` (faster-whisper, CTranslate2, RTF ~0.1), `openai` 备用 (RTF ~0.5), `funasr` 启动快但无时间戳\n\n"
        "**性能参考** (RTX 4090):\n"
        "- 首次请求会加载 Whisper-large-v3 模型 (~1.5GB CT2 / ~3GB pt), 约 30-60 秒\n"
        "- 后续请求复用内存中的模型, faster 引擎推理 RTF ≈ 0.1, openai ≈ 0.5"
    ),
    version="1.0.0",
)


# ---------------- 通用工具 ----------------

def _ok(data: Any) -> JSONResponse:
    return JSONResponse(content={"code": 0, "msg": "ok", "data": data})


def _err(msg: str, http_status: int = 500) -> JSONResponse:
    return JSONResponse(
        content={"code": -1, "msg": str(msg), "data": None},
        status_code=http_status,
    )


# ---------------- 请求模型 ----------------

class _SourceMixin(BaseModel):
    url: Optional[str] = Field(None, description="公网音视频 URL")
    path: Optional[str] = Field(None, description="服务器本地音视频路径")

    @model_validator(mode="after")
    def _check_one_of(self):
        if not self.url and not self.path:
            raise ValueError("必须提供 url 或 path 其中之一")
        return self

    def src(self) -> str:
        return self.url or self.path  # type: ignore[return-value]


class AsrAudioReq(_SourceMixin):
    language: Optional[str] = Field(None, description="thai/zh/en, 不传则自动检测")
    engine: str = Field("faster", description="faster (默认, RTF ~0.1) | openai (RTF ~0.5) | funasr")
    with_timestamps: bool = Field(True, description="faster / openai 引擎生效, 词级时间戳")


class AsrVideoReq(_SourceMixin):
    language: Optional[str] = None
    engine: str = Field("faster", description="faster (默认) | openai | funasr")


class ExtractReq(_SourceMixin):
    prefix: str = Field("chorify-video/audio", description="OSS key 前缀")


class TranslateReq(_SourceMixin):
    source: str = Field("thai", description="原语种, 默认 thai")
    target: str = Field("zh", description="目标语种, 默认 zh")
    engine: str = Field("faster", description="faster (默认) | openai | funasr")


class TTSReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="要合成的文本")
    voice_id: Optional[str] = Field(None, description="ElevenLabs voice id, 不传用默认 EST9Ui6982FZPSi7gCHi")
    model_id: Optional[str] = Field(None, description="默认 eleven_multilingual_v2")
    stability: float = Field(0.5, ge=0.0, le=1.0, description="0-1, 越高越平稳")
    similarity_boost: float = Field(0.75, ge=0.0, le=1.0, description="0-1, 越高越像参考音色")
    style: float = Field(0.0, ge=0.0, le=1.0, description="0-1, v2 模型情感强度")
    use_speaker_boost: bool = True
    output_format: str = Field("mp3_44100_128", description="mp3_44100_128/64, mp3_22050_32, pcm_*")
    upload: bool = Field(True, description="是否上传 OSS, false 时只在服务器本地落临时文件")


class MusicReq(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000, description="音乐描述, 英文效果更佳")
    music_length_ms: int = Field(30000, ge=10000, le=300000, description="时长毫秒, 10-300 秒")
    model_id: Optional[str] = Field(None, description="默认 music_v1")
    output_format: str = Field("mp3_44100_128", description="mp3_44100_128 / mp3_44100_64")
    upload: bool = Field(True, description="是否上传 OSS")


# ---------------- VoxCPM2 转发 ----------------

VOXCPM_BASE_URL = os.environ.get("VOXCPM_BASE_URL", "http://127.0.0.1:8190")
# VoxCPM2 单段合成在 4090 上通常 <2s, 但首次请求可能触发 5-10s 模型加载, 留充足超时
_voxcpm_client = httpx.Client(timeout=180.0)


class VoxcpmTtsReq(BaseModel):
    text: str = Field(..., min_length=1, description="正文; 开头加 '(描述)' 即 Voice Design 造音色")
    cfg_value: float = Field(2.0, description="越大越遵从文本, 通常 2.0")
    inference_timesteps: int = Field(10, description="越大越精细, 通常 10")


class VoxcpmClonePathReq(BaseModel):
    text: str = Field(..., min_length=1, description="目标文本")
    reference_wav_path: Optional[str] = Field(
        None,
        description="参考音 — 服务器本地路径 (e.g. I:/refs/a.wav) 或公网 URL (http(s)://...). "
                    "普通克隆模式必填; 终极克隆模式可选, 填同一份 prompt 音频可提升相似度"
    )
    prompt_wav_path: Optional[str] = Field(
        None,
        description="终极克隆: 参考音 (本地路径或 URL), 必须配 prompt_text 一起传"
    )
    prompt_text: Optional[str] = Field(
        None, description="终极克隆: 参考音对应的精确文本转写"
    )
    cfg_value: float = 2.0
    inference_timesteps: int = 10


# ---------------- 路由 ----------------

@app.get("/", tags=["misc"], summary="服务根路径")
def root():
    """返回服务基本信息，可作为存活探针。"""
    return _ok({"service": "asr", "status": "up", "docs": "/docs"})


@app.get("/health", tags=["misc"], summary="健康检查")
def health():
    """心跳接口，常用于 K8s liveness/readiness probe。返回 `{status: 'up'}`。"""
    return _ok({"service": "asr", "status": "up"})


@app.post("/asr/audio", tags=["asr"], summary="识别音频内容 → 文本 + 时间戳")
def api_asr_audio(req: AsrAudioReq):
    """
    把音频转写成文本。

    **何时用**: 你已经有音频文件 (wav / mp3 / m4a 等)，想拿到识别文本。

    **输入** (body):
    - `url`: 公网音频地址 (会下载到服务器临时文件)
    - `path`: 服务器本地音频路径 (二选一)
    - `language`: `thai` / `zh` / `en` ... 留空自动检测
    - `engine`: `openai` (默认带时间戳) 或 `funasr`
    - `with_timestamps`: 默认 `true`，关掉可省 30-50% 推理时间

    **返回** `data` 字段:
    ```json
    {
      "text": "完整文本",
      "segments": [
        {"start": 0.0, "end": 3.5, "text": "...",
         "words": [{"start": 0.0, "end": 0.2, "word": "...", "probability": 0.95}]}
      ]
    }
    ```
    """
    try:
        result = transcribe_audio(
            req.src(),
            language=req.language,
            engine=req.engine,
            with_timestamps=req.with_timestamps,
        )
        result.pop("raw", None)
        return _ok(result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.post("/asr/video", tags=["asr"], summary="识别视频内容 → 自动抽音 + 文本 + 时间戳")
def api_asr_video(req: AsrVideoReq):
    """
    视频转文本一条龙: 下载视频 → ffmpeg 抽 16k 单声道 WAV → Whisper 识别。

    **何时用**: 输入是视频 (mp4/mov/...), 想拿到讲了什么。

    **输入** (body):
    - `url` 或 `path`: 视频地址 (二选一)
    - `language`: 留空自动检测
    - `engine`: `openai` (默认) 或 `funasr`

    **返回结构** 同 `/asr/audio`，多了内部抽音步骤但对调用方透明。
    """
    try:
        result = transcribe_video(req.src(), language=req.language, engine=req.engine)
        result.pop("raw", None)
        return _ok(result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.post("/asr/extract", tags=["asr"], summary="视频抽音轨上传 OSS")
def api_extract(req: ExtractReq):
    """
    视频 → ffmpeg 抽 16k 单声道 WAV → 上传阿里云 OSS → 返回公网 URL。

    **何时用**:
    - 想把音频上 OSS 给别的服务调用 (例如豆包 ASR 那种只接受 URL 的接口)
    - 想把视频里的音频沉淀下来做后续二次加工

    **输入** (body):
    - `url` 或 `path`: 视频地址 (二选一)
    - `prefix`: OSS key 前缀, 默认 `chorify-video/audio`

    **返回**:
    ```json
    { "audio_url": "https://oss-imgai.sligenai.cn/chorify-video/audio/<md5>.wav" }
    ```

    输出音频规格: 16kHz / 单声道 / PCM 16-bit WAV (Whisper / 大多数 ASR 友好)。
    """
    try:
        url = extract_audio_to_oss(req.src(), prefix=req.prefix)
        return _ok({"audio_url": url})
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.post("/asr/translate", tags=["asr"], summary="一站式: 视频 → ASR → 豆包翻译")
def api_translate(req: TranslateReq):
    """
    端到端: 视频 → 抽音 → Whisper 识别 → 豆包翻译。

    **何时用**: 拿到外语视频 (如泰国电商带货), 想要一次得到原文 + 中文译文 + 时间轴。

    **输入** (body):
    - `url` 或 `path`: 视频地址 (二选一)
    - `source`: 原语种，默认 `thai`
    - `target`: 译入语种，默认 `zh`
    - `engine`: `openai` (默认带时间戳) 或 `funasr`

    **返回** `data` 字段:
    ```json
    {
      "source_text": "ในตอน... (泰文原文)",
      "target_text": "约会的时候... (中文译文, \\n 分段)",
      "source_language": "thai",
      "target_language": "zh",
      "segments": [
        {"start": 0.0, "end": 4.38, "text": "ในตอนออกเดท ...",
         "words": [{"start": 0.0, "end": 0.1, "word": "ใ", "probability": 0.7}]}
      ]
    }
    ```

    **耗时参考** (RTX 4090): 80-100s 视频约 20-30s (含翻译 1-3s)。
    """
    try:
        result = transcribe_and_translate(
            req.src(),
            source_language=req.source,
            target_language=req.target,
            engine=req.engine,
        )
        result.pop("raw_asr", None)
        return _ok(result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.post("/tts/speech", tags=["tts"], summary="ElevenLabs 文本转语音 → mp3 上 OSS")
def api_tts_speech(req: TTSReq):
    """
    把文本通过 ElevenLabs 合成为语音, 上传 OSS 后返回 URL。

    **何时用**: 短视频配音 / AI 主播台词 / 通知音播报。

    **输入** (body):
    - `text`: 文本 (1-5000 字)
    - `voice_id`: ElevenLabs voice id (留空 = `EST9Ui6982FZPSi7gCHi` 默认)。
      切换音色: 让用户去 https://elevenlabs.io/app/developers 复制目标 voice_id
    - `model_id`: 默认 `eleven_multilingual_v2`, 中泰英都支持
    - `stability` / `similarity_boost` / `style`: 音色参数
    - `output_format`: 默认 `mp3_44100_128`
    - `upload`: 默认 true, 走 OSS; false 时只在服务器本地落临时文件

    **返回** `data` 字段:
    ```json
    {
      "audio_url": "https://oss-imgai.sligenai.cn/chorify-video/tts/<md5>.mp3",
      "voice_id": "21m00Tcm4TlvDq8ikWAM",
      "model_id": "eleven_multilingual_v2",
      "bytes": 86432,
      "cost_ms": 2150,
      "output_format": "mp3_44100_128"
    }
    ```
    """
    try:
        result = synthesize_speech(
            text=req.text,
            voice_id=req.voice_id,
            model_id=req.model_id,
            stability=req.stability,
            similarity_boost=req.similarity_boost,
            style=req.style,
            use_speaker_boost=req.use_speaker_boost,
            output_format=req.output_format,
            upload=req.upload,
        )
        return _ok(result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.post("/tts/music", tags=["tts"], summary="ElevenLabs 文本生成音乐 → mp3 上 OSS")
def api_tts_music(req: MusicReq):
    """
    把文本提示通过 ElevenLabs Music 生成背景音乐, 上传 OSS 后返回 URL。

    **何时用**: 短视频 BGM / 开场片头 / 转场音乐 (不想买版权曲库时)。

    **输入** (body):
    - `prompt`: 音乐描述, **英文效果更佳** (e.g. `"upbeat lofi hip hop with rain ambience"`)
    - `music_length_ms`: 10000-300000 (10-300 秒)
    - `model_id`: 默认 `music_v1`
    - `output_format`: `mp3_44100_128` / `mp3_44100_64`
    - `upload`: 默认 true

    **返回** `data` 字段:
    ```json
    {
      "audio_url": "https://oss-imgai.sligenai.cn/chorify-video/music/<md5>.mp3",
      "music_length_ms": 30000,
      "model_id": "music_v1",
      "bytes": 491520,
      "cost_ms": 18230,
      "output_format": "mp3_44100_128"
    }
    ```

    **耗时**: 30s 音乐约 15-25s 生成。
    """
    try:
        result = generate_music(
            prompt=req.prompt,
            music_length_ms=req.music_length_ms,
            model_id=req.model_id,
            output_format=req.output_format,
            upload=req.upload,
        )
        return _ok(result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.get("/tts/voices", tags=["tts"], summary="列出 ElevenLabs 账户可用音色")
def api_tts_voices():
    """
    透传 ElevenLabs `GET /v1/voices`, 返回原始 JSON。

    用于前端做音色选择下拉框, 或调试时查 voice_id。
    """
    try:
        return _ok(tts_list_voices())
    except Exception as e:
        traceback.print_exc()
        return _err(e)


# ---------------- VoxCPM2 转发路由 ----------------
# 后端默认在 127.0.0.1:8190 (voxcpm/server.py), 通过环境变量 VOXCPM_BASE_URL 覆盖。
# 这里只做透传 + 错误标准化, 不解析音频内容; 响应都是 audio/wav 二进制。


def _voxcpm_relay_wav(method: str, path: str, **kwargs) -> Response:
    """统一转发 voxcpm 服务, 把 wav 二进制透传回客户端; 后端不可达/出错返回标准化 err JSON。"""
    url = f"{VOXCPM_BASE_URL}{path}"
    try:
        r = _voxcpm_client.request(method, url, **kwargs)
    except httpx.HTTPError as e:
        return _err(f"VoxCPM2 后端不可达 ({VOXCPM_BASE_URL}): {e}", http_status=502)
    if r.status_code != 200:
        # 透传后端错误信息 (FastAPI HTTPException 序列化的 detail)
        return _err(f"VoxCPM2 后端 {r.status_code}: {r.text[:300]}", http_status=r.status_code)
    return Response(content=r.content, media_type="audio/wav")


@app.get("/tts/voxcpm/health", tags=["tts"], summary="VoxCPM2 后端健康检查")
def api_voxcpm_health():
    """探活 voxcpm/server.py, 返回它的 /health JSON。"""
    try:
        r = _voxcpm_client.get(f"{VOXCPM_BASE_URL}/health", timeout=5.0)
        r.raise_for_status()
        return _ok(r.json())
    except httpx.HTTPError as e:
        return _err(f"VoxCPM2 后端不可达 ({VOXCPM_BASE_URL}): {e}", http_status=502)


@app.post("/tts/voxcpm", tags=["tts"], summary="VoxCPM2 文本转语音 / Voice Design")
def api_voxcpm_tts(req: VoxcpmTtsReq):
    """
    基础 TTS。`text` 开头加 `(描述)` 启用 **Voice Design** 模式 (例: `"(温柔甜美的年轻女性)你好"`)。

    返回 `audio/wav` 二进制 (sample_rate=16000)。
    """
    return _voxcpm_relay_wav("POST", "/tts", json=req.model_dump())


@app.post("/tts/voxcpm/clone_path", tags=["tts"], summary="VoxCPM2 本地路径音色克隆 (含终极克隆)")
def api_voxcpm_clone_path(req: VoxcpmClonePathReq):
    """
    用服务器本地音频路径做参考音, **不用上传**, chorify 批量配音流水线推荐。

    两种模式 (二选一或都传):
      - **普通克隆**: 只填 `reference_wav_path`
      - **终极克隆 (最高保真)**: 填 `prompt_wav_path` + `prompt_text`
        (官方推荐 `reference_wav_path` 也填同一份音频以提升相似度)

    返回 `audio/wav` 二进制。
    """
    return _voxcpm_relay_wav("POST", "/clone_path", json=req.model_dump())


@app.post("/tts/voxcpm/clone", tags=["tts"], summary="VoxCPM2 上传参考音色克隆 (multipart)")
async def api_voxcpm_clone(
    text: str = Form(..., description="目标文本"),
    reference: UploadFile = File(..., description="参考音频 (wav/mp3, 建议 ≥3s)"),
    cfg_value: float = Form(2.0),
    inference_timesteps: int = Form(10),
    prompt_reference: Optional[UploadFile] = File(
        None, description="终极克隆: 额外参考音文件, 必须配 prompt_text"
    ),
    prompt_text: Optional[str] = Form(None, description="终极克隆: 参考音对应的精确文本"),
):
    """
    上传参考音文件 + 文本, 克隆音色。临时调试场景适用; 批量场景请用 `/tts/voxcpm/clone_path`。

    返回 `audio/wav` 二进制。
    """
    # 透传 multipart 给 voxcpm 后端
    files = [("reference", (reference.filename or "ref.wav",
                            await reference.read(),
                            reference.content_type or "application/octet-stream"))]
    data = {
        "text": text,
        "cfg_value": str(cfg_value),
        "inference_timesteps": str(inference_timesteps),
    }
    if prompt_reference is not None:
        files.append(("prompt_reference",
                      (prompt_reference.filename or "prompt.wav",
                       await prompt_reference.read(),
                       prompt_reference.content_type or "application/octet-stream")))
        if prompt_text:
            data["prompt_text"] = prompt_text
    return _voxcpm_relay_wav("POST", "/clone", data=data, files=files)


# ---------------- 启动入口 ----------------

def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--reload", action="store_true", help="热重载, 仅开发用")
    parser.add_argument("--workers", type=int, default=1, help="进程数 (注意: 模型会按进程加载)")
    args = parser.parse_args()
    print(f"[asr-api] starting on http://{args.host}:{args.port}  (docs: /docs)")
    uvicorn.run(
        "ailab.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
