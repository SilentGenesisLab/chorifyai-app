# -*- coding: utf-8 -*-
"""
VoxCPM2 轻量 HTTP 服务,供 chorify 后端通过 HTTP 调用。
启动:  start_server.bat   (默认 0.0.0.0:8190, 用 tor25 环境)

接口:
  GET  /health                      健康检查
  POST /tts          json           文本转语音 / Voice Design (text 开头加"(描述)"即造音色)
  POST /clone        multipart      上传参考音 + 文本, 克隆音色
                                    可选 prompt_reference + prompt_text 启用"终极克隆"
  POST /clone_path   json           用本地路径 / 公网 URL 克隆 (批量场景推荐), 同样支持终极克隆
                                    reference_wav_path / prompt_wav_path 接受:
                                      - 服务器本地路径    "I:/path/to/voice.wav"
                                      - 公网 URL          "https://oss.../voice.mp3"

返回均为 audio/wav 二进制流 (sample_rate=16000)。

VoxCPM2 四种合成模式速查:
  1) 基础 TTS              text 即可
  2) Voice Design          text="(描述)正文"
  3) 普通克隆              + reference_wav_path
  4) 终极克隆 (最高保真)    + prompt_wav_path + prompt_text (建议 reference_wav_path 也填同一份)
"""
import io
import os
import tempfile
import argparse
from typing import Optional

import numpy as np
import soundfile as sf
import torch

# Windows + voxcpm + torch.compile 短期不可用 — 已知撞多个上游 ABI 不兼容:
#   - torch 2.5.x: codecache.write_atomic 用 os.rename, Windows 不能覆盖 (FileExistsError)
#   - torch 2.8.0 + triton-windows 3.7: 缺 triton.compiler.compiler.triton_key (可 monkey-patch)
#   - torch 2.8.0 + triton-windows 3.7: KernelMetadata 缺 cluster_dims 属性 (Hopper 特性,
#                                       runtime 缺失, 无法用 monkey-patch 修, 每个 kernel 都要)
# 结论: Windows 上 voxcpm 走 eager 模式, RTF ~2.0 完全够批量配音用. Linux docker 部署
# 用官方 triton 跟 PyTorch ABI 一致, 那边可以恢复 torch.compile.
_torch_ver = tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2])
if os.name == "nt":
    print(f"[init] torch {torch.__version__}, disable torch.compile on Windows (triton-windows ABI mismatch)")

    def _noop_compile(model=None, *args, **kwargs):
        if model is None:
            return lambda m: m   # 作为装饰器 @torch.compile(...) 用
        return model             # 作为函数 torch.compile(module) 用
    torch.compile = _noop_compile

    import torch._dynamo
    torch._dynamo.config.disable = True
    torch._dynamo.config.suppress_errors = True
else:
    print(f"[init] torch {torch.__version__} on {os.name}, torch.compile 保留")

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from voxcpm import VoxCPM

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("VOXCPM_MODEL_DIR", os.path.join(HERE, "models", "VoxCPM2"))

app = FastAPI(title="VoxCPM2 Service", version="1.0")
_model = None
_sr = 16000


# 强制 line-buffered, 避免被 supervisor PIPE 吞掉 print/traceback
import sys as _sys
try:
    _sys.stdout.reconfigure(line_buffering=True)
    _sys.stderr.reconfigure(line_buffering=True)
except AttributeError:
    pass


# 全局异常 handler: 把 traceback 写到 stderr + 塞进 JSON 响应, 调试期间方便定位
import traceback as _tb
from fastapi import Request as _Req

@app.exception_handler(Exception)
async def _unhandled_exc(request: _Req, exc: Exception):
    tb = _tb.format_exc()
    _sys.stderr.write(f"\n=== UNHANDLED on {request.method} {request.url.path} ===\n{tb}\n")
    _sys.stderr.flush()
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__,
            "traceback": tb,
        },
    )


def get_model():
    global _model, _sr
    if _model is None:
        print(f"[init] loading VoxCPM2 from {MODEL_DIR} ...")
        _model = VoxCPM.from_pretrained(MODEL_DIR, load_denoiser=False)
        _sr = _model.tts_model.sample_rate
        print(f"[init] ready, sample_rate={_sr}Hz, cuda={torch.cuda.is_available()}")
    return _model


def wav_bytes(wav: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV")
    return buf.getvalue()


# ============ 音频输入解析 (本地路径 / URL 二合一) ============

_URL_PREFIXES = ("http://", "https://")
# 按 Content-Type 推断文件后缀, 给 VoxCPM 加载用 (内部按后缀走解码后端)
_CT_TO_SUFFIX = {
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav",
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
    "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac",
    "audio/ogg": ".ogg", "audio/flac": ".flac", "audio/x-flac": ".flac",
    "video/mp4": ".mp4", "application/octet-stream": ".wav",  # OSS 经常返回 octet-stream
}


def _is_url(s: str) -> bool:
    return isinstance(s, str) and s.lower().startswith(_URL_PREFIXES)


def _download_to_temp(url: str, max_bytes: int = 200 * 1024 * 1024) -> str:
    """下载 URL 到临时文件, 返回路径。max_bytes 限制大文件 (默认 200MB)。"""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "voxcpm/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 200:
                raise HTTPException(502, f"下载 {url} 失败: HTTP {resp.status}")
            ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            # URL 末尾后缀优先, content-type 兜底, 都没有用 .wav
            url_suffix = os.path.splitext(url.split("?")[0])[1].lower()
            suffix = url_suffix if url_suffix in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".mp4"} \
                else _CT_TO_SUFFIX.get(ct, ".wav")
            # 流式读, 避免大文件 OOM
            total = 0
            chunk = 1024 * 64
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    total += len(buf)
                    if total > max_bytes:
                        tmp.close()
                        os.remove(tmp.name)
                        raise HTTPException(413, f"音频过大 (> {max_bytes // 1024 // 1024} MB): {url}")
                    tmp.write(buf)
                return tmp.name
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"下载 {url} 失败: {type(e).__name__}: {e}")


def _resolve_audio_input(value: Optional[str]):
    """
    解析音频输入字段: 本地路径直接用; http(s):// 自动下载到临时文件。
    返回 (本地路径, 是否需要清理临时文件), value 为空返回 (None, False)。
    """
    if not value:
        return None, False
    if _is_url(value):
        return _download_to_temp(value), True
    if not os.path.exists(value):
        raise HTTPException(404, f"音频文件不存在: {value}")
    return value, False


class TTSReq(BaseModel):
    text: str
    cfg_value: float = 2.0
    inference_timesteps: int = 10


class ClonePathReq(BaseModel):
    text: str
    # 普通克隆: 只填 reference_wav_path
    # 字段名为兼容历史保留 "_wav_path", 实际接受:
    #   - 服务器本地路径    "I:/path/to/voice.wav"
    #   - 公网 URL          "https://example.com/voice.mp3" / "https://oss-xxx.aliyuncs.com/..."
    reference_wav_path: Optional[str] = None
    # 终极克隆: 同时填 prompt_wav_path + prompt_text;
    # reference_wav_path 也填同一份音频可获得更高相似度 (官方推荐)
    prompt_wav_path: Optional[str] = None
    prompt_text: Optional[str] = None
    cfg_value: float = 2.0
    inference_timesteps: int = 10


@app.get("/health")
def health():
    return {"status": "ok", "cuda": torch.cuda.is_available(), "model_dir": MODEL_DIR,
            "loaded": _model is not None}


@app.post("/tts")
def tts(req: TTSReq):
    if not req.text.strip():
        raise HTTPException(400, "text 不能为空")
    m = get_model()
    wav = m.generate(text=req.text, cfg_value=req.cfg_value,
                     inference_timesteps=req.inference_timesteps)
    return Response(content=wav_bytes(wav, _sr), media_type="audio/wav")


async def _save_upload(upload: UploadFile) -> str:
    """把 UploadFile 写到临时文件, 返回路径。调用方记得清理。"""
    suffix = os.path.splitext(upload.filename or "ref.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await upload.read())
        return tmp.name


def _safe_unlink(path: Optional[str]):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


@app.post("/clone")
async def clone(
    text: str = Form(...),
    reference: UploadFile = File(...),
    cfg_value: float = Form(2.0),
    inference_timesteps: int = Form(10),
    # 终极克隆模式 (可选): 同时上传 prompt_reference 文件 + prompt_text 转写
    prompt_reference: Optional[UploadFile] = File(None),
    prompt_text: Optional[str] = Form(None),
):
    if not text.strip():
        raise HTTPException(400, "text 不能为空")
    if prompt_reference is not None and not (prompt_text or "").strip():
        raise HTTPException(400, "prompt_reference 必须配合 prompt_text 一起传 (终极克隆模式)")

    m = get_model()
    ref_path = await _save_upload(reference)
    prompt_path: Optional[str] = await _save_upload(prompt_reference) if prompt_reference is not None else None
    try:
        kwargs = dict(
            text=text,
            reference_wav_path=ref_path,
            cfg_value=cfg_value,
            inference_timesteps=inference_timesteps,
        )
        if prompt_path:
            kwargs["prompt_wav_path"] = prompt_path
            kwargs["prompt_text"] = prompt_text
        wav = m.generate(**kwargs)
    finally:
        _safe_unlink(ref_path)
        _safe_unlink(prompt_path)
    return Response(content=wav_bytes(wav, _sr), media_type="audio/wav")


@app.post("/clone_path")
def clone_path(req: ClonePathReq):
    if not req.text.strip():
        raise HTTPException(400, "text 不能为空")
    if not (req.reference_wav_path or req.prompt_wav_path):
        raise HTTPException(400, "reference_wav_path 或 prompt_wav_path 至少要传一个")
    if req.prompt_wav_path and not (req.prompt_text or "").strip():
        raise HTTPException(400, "prompt_wav_path 必须配合 prompt_text 一起传 (终极克隆模式)")

    # 解析输入: 本地路径直接用; URL 下载到临时文件 (用完清理)
    ref_path,    ref_is_tmp    = _resolve_audio_input(req.reference_wav_path)
    prompt_path, prompt_is_tmp = _resolve_audio_input(req.prompt_wav_path)

    tmp_to_clean = []
    if ref_is_tmp:    tmp_to_clean.append(ref_path)
    if prompt_is_tmp: tmp_to_clean.append(prompt_path)

    try:
        m = get_model()
        kwargs = dict(
            text=req.text,
            cfg_value=req.cfg_value,
            inference_timesteps=req.inference_timesteps,
        )
        if ref_path:
            kwargs["reference_wav_path"] = ref_path
        if prompt_path:
            kwargs["prompt_wav_path"] = prompt_path
            kwargs["prompt_text"] = req.prompt_text
        wav = m.generate(**kwargs)
        return Response(content=wav_bytes(wav, _sr), media_type="audio/wav")
    finally:
        for p in tmp_to_clean:
            _safe_unlink(p)


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8190)
    parser.add_argument("--preload", action="store_true", help="启动时即加载模型")
    args = parser.parse_args()
    if args.preload:
        get_model()
    uvicorn.run(app, host=args.host, port=args.port)
