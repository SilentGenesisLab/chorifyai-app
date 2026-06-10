"""视频拆分 — 按画面(PySceneDetect) / 按时间 / 按口播。

流程：下载已上传到 OSS 的视频 → 检测分段 → ffmpeg 切片 + 取缩略图 → 上传 OSS → 返回切片列表。
按画面用 PySceneDetect 的 ContentDetector；按时间按固定时长均分；按口播暂复用画面检测占位。
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

from app.core.config import settings
from app.services.local_storage import maybe_local_path, object_path
from app.services.oss import put_object

router = APIRouter(prefix="/api/split", tags=["split"])

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


class SplitRequest(BaseModel):
    url: str
    method: str = "scene"  # scene | time | speech
    threshold: float = 27.0  # PySceneDetect 内容阈值（越小切得越碎）
    interval: float = 10.0  # 秒，按时间拆分的片段时长
    make_clips: bool = True  # 是否用 ffmpeg 真实切片并上传
    max_clips: int = 80


class Clip(BaseModel):
    index: int
    start: float
    end: float
    duration: float
    url: str | None = None
    thumbnail: str | None = None
    localPath: str | None = None


# 拆分任务存储（内存，单进程 uvicorn 足够）：job_id -> {status, method, count, has_clips, clips, error}
_JOBS: dict[str, dict] = {}


def _download(url: str) -> str:
    suffix = os.path.splitext(url.split("?")[0])[1] or ".mp4"
    fd, path = tempfile.mkstemp(suffix=suffix)
    local = maybe_local_path(url)
    if local:
        os.close(fd)
        shutil.copyfile(local, path)
        return path
    try:
        with requests.get(url, stream=True, timeout=180) as r:
            r.raise_for_status()
            with os.fdopen(fd, "wb") as f:
                for chunk in r.iter_content(1 << 16):  # 流式下载在 try 内，连接重置也能兜住
                    if chunk:
                        f.write(chunk)
        return path
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail=f"下载视频失败：{e}")


def _probe_duration(path: str) -> float:
    try:
        from scenedetect import open_video

        v = open_video(path)
        return float(v.duration.get_seconds()) if v.duration else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _scene_segments(path: str, threshold: float) -> list[tuple[float, float]]:
    from scenedetect import ContentDetector, detect  # 延迟导入，未装时给出友好提示

    scenes = detect(path, ContentDetector(threshold=threshold))
    segs = [(s.get_seconds(), e.get_seconds()) for s, e in scenes]
    if not segs:  # 单一长镜头：整段作为一个切片
        dur = _probe_duration(path)
        segs = [(0.0, dur)] if dur > 0 else []
    return segs


def _time_segments(path: str, interval: float) -> list[tuple[float, float]]:
    dur = _probe_duration(path)
    if dur <= 0:
        return []
    segs: list[tuple[float, float]] = []
    t = 0.0
    while t < dur - 0.05:
        segs.append((t, min(t + interval, dur)))
        t += interval
    return segs


def _ffmpeg(args: list[str]) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", *args],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _put_retry(key: str, data: bytes, content_type: str, tries: int = 3) -> str:
    """OSS 上传带重试 —— 抵御偶发的连接重置 (ConnectionResetError 10054)。"""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            return put_object(key, data, content_type)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise last if last else RuntimeError("OSS upload failed")


def _cut_and_upload(path: str, segments: list[tuple[float, float]], day: str) -> list[Clip]:
    clips: list[Clip] = []
    tmpdir = tempfile.mkdtemp()
    try:
        for i, (start, end) in enumerate(segments):
            dur = max(0.0, end - start)
            clip = Clip(
                index=i + 1,
                start=round(start, 2),
                end=round(end, 2),
                duration=round(dur, 2),
            )
            # 单个切片的切割/上传失败不应让整次请求崩溃：失败则保留时间区间、跳过 url。
            if _HAS_FFMPEG and dur > 0.05:
                base = uuid.uuid4().hex
                out = os.path.join(tmpdir, f"{base}.mp4")
                thumb = os.path.join(tmpdir, f"{base}.jpg")
                try:
                    if _ffmpeg(
                        ["-ss", f"{start}", "-i", path, "-t", f"{dur}",
                         "-c", "copy", "-avoid_negative_ts", "1", out]
                    ) and os.path.exists(out):
                        with open(out, "rb") as f:
                            clip_key = f"splits/{day}/{base}.mp4"
                            clip.url = _put_retry(clip_key, f.read(), "video/mp4")
                            clip.localPath = object_path(clip_key)
                    if _ffmpeg(
                        ["-ss", f"{start + dur / 2}", "-i", path, "-frames:v", "1", "-q:v", "3", thumb]
                    ) and os.path.exists(thumb):
                        with open(thumb, "rb") as f:
                            clip.thumbnail = _put_retry(f"splits/{day}/{base}.jpg", f.read(), "image/jpeg")
                except Exception as e:  # noqa: BLE001
                    print(f"[split] 切片 {i + 1} 处理失败（已跳过 url）：{e}")
            clips.append(clip)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return clips


def _run_job(job_id: str, req: SplitRequest) -> None:
    """后台线程执行拆分；结果写入 _JOBS（避免长请求被代理 30s 超时）。"""
    path: str | None = None
    try:
        path = _download(req.url)  # 失败 → HTTPException(400)
        if req.method == "time":
            segs = _time_segments(path, max(1.0, req.interval))
        else:
            # scene（默认）；speech 暂复用画面检测占位
            segs = _scene_segments(path, req.threshold)
        if not segs:
            raise HTTPException(status_code=422, detail="未能从该视频检测到可拆分片段")
        segs = segs[: max(1, req.max_clips)]

        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        if req.make_clips:
            clips = _cut_and_upload(path, segs, day)
        else:
            clips = [
                Clip(index=i + 1, start=round(s, 2), end=round(e, 2), duration=round(e - s, 2))
                for i, (s, e) in enumerate(segs)
            ]
        _JOBS[job_id] = {
            "status": "done",
            "method": req.method,
            "count": len(clips),
            "has_clips": any(c.url for c in clips),
            "clips": [c.model_dump() for c in clips],
        }
    except ImportError:
        _JOBS[job_id] = {
            "status": "failed",
            "error": "后端未安装 scenedetect，请：pip install scenedetect opencv-python-headless",
        }
    except HTTPException as e:
        _JOBS[job_id] = {"status": "failed", "error": str(e.detail)}
    except Exception as e:  # noqa: BLE001
        print(f"[split] 任务 {job_id} 失败：{e}")
        _JOBS[job_id] = {"status": "failed", "error": f"拆分处理失败：{e}"}
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


@router.post("")
def start_split(req: SplitRequest) -> dict:
    """启动拆分任务，立即返回 job_id（请求很短，不会触发代理超时）。"""
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "processing", "method": req.method}
    threading.Thread(target=_run_job, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id, "status": "processing"}


@router.get("/{job_id}")
def get_split(job_id: str) -> dict:
    """轮询拆分任务状态/结果。"""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return job
