"""合成量产 — 智能混剪。把每个镜头分组随机抽到的一条片段按顺序拼成一条成片。

流程：接收一组片段 URL（OSS）→ 逐条归一化(缩放/补边到目标分辨率 + 统一帧率/音频)
→ concat 拼接 → 上传 OSS → 返回成片 URL。异步 job + 轮询（同 split）。

稳健性：
- 全局信号量限制并发 ffmpeg（避免一次合成多条时 CPU/IO 争用导致部分失败）
- 下载带重试（抵御 OSS/CDN 偶发连接重置）
- 捕获 ffmpeg stderr，失败时回传具体原因
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
from app.services.oss import put_object

router = APIRouter(prefix="/api/mix", tags=["mix"])

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None

# 最多同时跑 2 条合成的重活（每条内部还会串行处理各片段），其余排队，避免争用失败
_SEM = threading.Semaphore(2)

# job_id -> {status: processing|done|failed, url?, error?}
_JOBS: dict[str, dict] = {}


class MixRequest(BaseModel):
    clips: list[str]
    width: int = 1080
    height: int = 1920
    name: str | None = None


def _download(url: str, dst_dir: str, idx: int, tries: int = 3) -> str:
    suffix = os.path.splitext(url.split("?")[0])[1] or ".mp4"
    path = os.path.join(dst_dir, f"src_{idx}{suffix}")
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with requests.get(url, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
            if os.path.getsize(path) > 0:
                return path
            last = RuntimeError("下载到空文件")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"下载片段失败：{last}")


def _ffmpeg(args: list[str], timeout: int = 600) -> tuple[bool, str]:
    """运行 ffmpeg，返回 (是否成功, stderr 末尾片段)。"""
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
    common = ["-vsync", "cfr", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
              "-c:a", "aac", "-ar", "44100", "-ac", "2", "-movflags", "+faststart"]
    if _has_audio(src):
        cmd = ["-i", src, "-vf", vf, "-map", "0:v:0", "-map", "0:a:0", *common, dst]
    else:
        cmd = ["-i", src, "-f", "lavfi", "-i",
               "anullsrc=channel_layout=stereo:sample_rate=44100",
               "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-shortest", *common, dst]
    return _ffmpeg(cmd)


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
    with _SEM:  # 限制并发重活
        work = tempfile.mkdtemp(prefix="mix_")
        try:
            norm_parts: list[str] = []
            for i, url in enumerate(req.clips):
                src = _download(url, work, i)
                out = os.path.join(work, f"n_{i}.mp4")
                ok, err = _normalize(src, out, req.width, req.height)
                if not ok or not os.path.exists(out):
                    raise RuntimeError(f"第 {i + 1} 段处理失败：{err or '未知'}")
                norm_parts.append(out)

            final = os.path.join(work, "final.mp4")
            ok, err = _concat(norm_parts, final)
            if not ok or not os.path.exists(final):
                raise RuntimeError(f"拼接失败：{err or '未知'}")

            thumb_url = video_thumbnail_url(final)
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            key = f"mix/{day}/{uuid.uuid4().hex}.mp4"
            with open(final, "rb") as f:
                url = put_object(key, f.read(), "video/mp4")
            _JOBS[job_id] = {
                "status": "done", "url": url, "key": key, "thumbnailUrl": thumb_url,
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
