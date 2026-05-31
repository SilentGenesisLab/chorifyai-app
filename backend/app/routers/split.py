"""视频拆分 — 按画面(PySceneDetect) / 按时间 / 按口播。

流程：下载已上传到 OSS 的视频 → 检测分段 → ffmpeg 切片 + 取缩略图 → 上传 OSS → 返回切片列表。
按画面用 PySceneDetect 的 ContentDetector；按时间按固定时长均分；按口播暂复用画面检测占位。
"""
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
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


class SplitResponse(BaseModel):
    method: str
    count: int
    has_clips: bool
    clips: list[Clip]


def _download(url: str) -> str:
    try:
        r = requests.get(url, stream=True, timeout=180)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"下载视频失败：{e}")
    suffix = os.path.splitext(url.split("?")[0])[1] or ".mp4"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk)
    return path


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
            if _HAS_FFMPEG and dur > 0.05:
                base = uuid.uuid4().hex
                out = os.path.join(tmpdir, f"{base}.mp4")
                thumb = os.path.join(tmpdir, f"{base}.jpg")
                if _ffmpeg(
                    ["-ss", f"{start}", "-i", path, "-t", f"{dur}",
                     "-c", "copy", "-avoid_negative_ts", "1", out]
                ) and os.path.exists(out):
                    with open(out, "rb") as f:
                        clip.url = put_object(f"splits/{day}/{base}.mp4", f.read(), "video/mp4")
                if _ffmpeg(
                    ["-ss", f"{start + dur / 2}", "-i", path, "-frames:v", "1", "-q:v", "3", thumb]
                ) and os.path.exists(thumb):
                    with open(thumb, "rb") as f:
                        clip.thumbnail = put_object(f"splits/{day}/{base}.jpg", f.read(), "image/jpeg")
            clips.append(clip)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return clips


@router.post("", response_model=SplitResponse)
def split(req: SplitRequest) -> SplitResponse:
    path = _download(req.url)
    try:
        if req.method == "time":
            segs = _time_segments(path, max(1.0, req.interval))
        else:
            # scene（默认）；speech 暂复用画面检测占位
            try:
                segs = _scene_segments(path, req.threshold)
            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="后端未安装 scenedetect，请：pip install scenedetect opencv-python-headless",
                )
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
        return SplitResponse(
            method=req.method,
            count=len(clips),
            has_clips=any(c.url for c in clips),
            clips=clips,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
