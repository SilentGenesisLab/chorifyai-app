"""视频缩略图：ffmpeg 截取首帧 → JPG → 上传 OSS，返回公网 url。

所有进入 OSS 的视频都生成一张首帧缩略图，前端列表/组合用它做封面。
"""
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

from app.services.oss import put_object

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def video_thumbnail_url(video_path: str) -> str | None:
    """从本地视频文件截首帧 → 上传 OSS → 返回缩略图 url；失败返回 None。"""
    if not _HAS_FFMPEG or not os.path.exists(video_path):
        return None
    thumb = video_path + ".thumb.jpg"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "0", "-i", video_path,
             "-frames:v", "1", "-q:v", "4", "-vf", "scale=360:-2", thumb],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True,
        )
        if not os.path.exists(thumb) or os.path.getsize(thumb) == 0:
            return None
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"thumbs/{day}/{uuid.uuid4().hex}.jpg"
        with open(thumb, "rb") as f:
            return put_object(key, f.read(), "image/jpeg")
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            os.remove(thumb)
        except OSError:
            pass


def video_thumbnail_url_from_bytes(data: bytes, ext: str = ".mp4") -> str | None:
    """从视频二进制截首帧缩略图（先落临时文件）。"""
    fd, path = tempfile.mkstemp(suffix=ext or ".mp4")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return video_thumbnail_url(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
