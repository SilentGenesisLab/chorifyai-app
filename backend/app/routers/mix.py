"""合成量产 — 智能混剪。把每个镜头分组随机抽到的一条片段按顺序拼成一条成片。

性能关键（随机组合场景：少量素材、大量组合）：
- 归一化结果按 (url,分辨率) 缓存：同一片段只下载+转码一次，所有组合复用 → 不再每条成片都重转
- 有 NVIDIA 显卡时用 NVENC 硬件编码（4090 上 1080p 几乎实时）
- 拼接走 concat copy（不重编码）→ 单条成片基本只剩“拼接”开销
- 信号量限制并发转码，下载带重试，捕获 ffmpeg 错误
真实拼接依赖系统安装 ffmpeg。
"""
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.media import video_thumbnail_url
from app.services.local_storage import copy_or_download_to, object_path
from app.services.oss import put_object

router = APIRouter(prefix="/api/mix", tags=["mix"])

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None


def _detect_nvenc() -> bool:
    """真正跑一帧 NVENC 编码再判定 —— 仅「编码器已编入 ffmpeg」不代表有可用 GPU，
    无显卡服务器上 h264_nvenc 仍会列出但运行即失败（会导致合成报错）。"""
    if not _HAS_FFMPEG:
        return False
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-f", "lavfi",
             "-i", "color=c=black:s=64x64:d=0.1:r=5",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, timeout=20,
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


_HAS_NVENC = _detect_nvenc()

# 同时转码的并发上限（NVENC 下可适当放宽）
_SEM = threading.Semaphore(3 if _HAS_NVENC else 2)

# 归一化结果缓存：cache_key -> 本地 mp4 路径；同片段同分辨率只转一次，多组合复用
_NORM_DIR = tempfile.mkdtemp(prefix="mix_norm_")
_norm_cache: dict[str, str] = {}
_norm_locks: dict[str, threading.Lock] = {}
_norm_guard = threading.Lock()

# job_id -> {status, url?, thumbnailUrl?, error?}
_JOBS: dict[str, dict] = {}


class MixRequest(BaseModel):
    clips: list[str]
    width: int = 1080
    height: int = 1920
    name: str | None = None


def _download(url: str, dst: str, tries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with requests.get(url, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(dst, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
            if os.path.getsize(dst) > 0:
                return dst
            last = RuntimeError("下载到空文件")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"下载片段失败：{last}")


def _materialize_clip(url: str, dst: str) -> str:
    return copy_or_download_to(url, dst, _download)


def _ffmpeg(args: list[str], timeout: int = 600) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            ["ffmpeg", "-y", *args], capture_output=True, text=True, timeout=timeout
        )
        if p.returncode == 0:
            return True, ""
        return False, (p.stderr or "")[-400:].strip()
    except subprocess.TimeoutExpired:
        return False, "ffmpeg 处理超时"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _has_audio(path: str) -> bool:
    if not _HAS_FFPROBE:
        return True
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        ).stdout
        return bool(out.strip())
    except Exception:  # noqa: BLE001
        return True


def _normalize(src: str, dst: str, w: int, h: int) -> tuple[bool, str]:
    """统一到 w×h / 30fps(CFR) / h264 + aac 立体声；缺音轨补静音，保证 concat 不崩。"""
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
    )
    if _HAS_NVENC:
        vcodec = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"]
    else:
        vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    common = ["-vsync", "cfr", *vcodec, "-c:a", "aac", "-ar", "44100", "-ac", "2",
              "-movflags", "+faststart"]
    if _has_audio(src):
        cmd = ["-i", src, "-vf", vf, "-map", "0:v:0", "-map", "0:a:0", *common, dst]
    else:
        cmd = ["-i", src, "-f", "lavfi", "-i",
               "anullsrc=channel_layout=stereo:sample_rate=44100",
               "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-shortest", *common, dst]
    return _ffmpeg(cmd)


def _get_normalized(url: str, w: int, h: int) -> str:
    """下载并归一化某片段，结果缓存复用（同 url+分辨率只做一次）。返回本地路径。"""
    key = f"{url}|{w}x{h}"
    with _norm_guard:
        cached = _norm_cache.get(key)
        if cached and os.path.exists(cached):
            return cached
        lock = _norm_locks.setdefault(key, threading.Lock())
    with lock:
        cached = _norm_cache.get(key)
        if cached and os.path.exists(cached):
            return cached
        tmp = tempfile.mkdtemp(dir=_NORM_DIR)
        try:
            suffix = os.path.splitext(url.split("?")[0])[1] or ".mp4"
            src = _materialize_clip(url, os.path.join(tmp, f"src{suffix}"))
            out = os.path.join(_NORM_DIR, uuid.uuid4().hex + ".mp4")
            ok, err = _normalize(src, out, w, h)
            if not ok or not os.path.exists(out):
                raise RuntimeError(f"片段处理失败：{err or '未知'}")
            _norm_cache[key] = out
            return out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)  # 删源文件，保留归一化结果


def _concat(parts: list[str], dst: str) -> tuple[bool, str]:
    listfile = dst + ".txt"
    with open(listfile, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.replace(chr(92), '/')}'\n")
    ok, err = _ffmpeg(["-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy",
                       "-movflags", "+faststart", dst])
    try:
        os.remove(listfile)
    except OSError:
        pass
    return ok, err


def _run_mix(job_id: str, req: MixRequest) -> None:
    if not _HAS_FFMPEG:
        _JOBS[job_id] = {"status": "failed", "error": "服务器未安装 ffmpeg，无法合成"}
        return
    with _SEM:
        work = tempfile.mkdtemp(prefix="mix_")
        try:
            # 归一化（带缓存）：第 N 条成片若用到已转过的片段则秒取
            parts = [_get_normalized(url, req.width, req.height) for url in req.clips]

            final = os.path.join(work, "final.mp4")
            ok, err = _concat(parts, final)
            if not ok or not os.path.exists(final):
                raise RuntimeError(f"拼接失败：{err or '未知'}")

            thumb_url = video_thumbnail_url(final)
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            key = f"mix/{day}/{uuid.uuid4().hex}.mp4"
            with open(final, "rb") as f:
                url = put_object(key, f.read(), "video/mp4")
            _JOBS[job_id] = {
                "status": "done",
                "url": url,
                "key": key,
                "localPath": object_path(key),
                "thumbnailUrl": thumb_url,
            }
        except Exception as e:  # noqa: BLE001
            _JOBS[job_id] = {"status": "failed", "error": str(e)}
        finally:
            shutil.rmtree(work, ignore_errors=True)


@router.post("")
def start_mix(req: MixRequest) -> dict:
    """启动一条成片合成，立即返回 job_id（请求很短，不触发代理超时）。"""
    clips = [c for c in (req.clips or []) if c and c.strip()]
    if not clips:
        raise HTTPException(status_code=400, detail="没有可合成的片段")
    req.clips = clips
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "processing"}
    threading.Thread(target=_run_mix, args=(job_id, req), daemon=True).start()
    return {"ok": True, "job_id": job_id, "status": "processing"}


@router.get("/{job_id}")
def get_mix(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {"ok": job.get("status") == "done", **job}
