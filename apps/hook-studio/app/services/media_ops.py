from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

import httpx


class MediaOperationError(RuntimeError):
    code = "MEDIA_OPERATION_FAILED"


async def download(url: str, target: Path, *, max_bytes: int = 1024 * 1024 * 1024) -> Path:
    total = 0
    async with httpx.AsyncClient(timeout=120, follow_redirects=True, trust_env=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise MediaOperationError("媒体文件超过允许大小")
                    handle.write(chunk)
    return target


async def run_ffmpeg(arguments: Iterable[str]) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise MediaOperationError("服务器未安装ffmpeg")
    process = await asyncio.create_subprocess_exec(
        executable, "-hide_banner", "-loglevel", "error", "-y", *arguments,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode:
        raise MediaOperationError(stderr.decode("utf-8", errors="replace")[-1000:] or "ffmpeg执行失败")


async def replace_audio_file(video_url: str, audio_url: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="hook-audio-") as temp:
        root = Path(temp); video = root / "source.mp4"; audio = root / "voice.mp3"; output = root / "result.mp4"
        await asyncio.gather(download(video_url, video), download(audio_url, audio, max_bytes=100 * 1024 * 1024))
        await run_ffmpeg(["-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])
        return output.read_bytes()


async def replace_segment_file(source_url: str, replacement_url: str, *, start: float, end: float) -> bytes:
    if start < 0 or end <= start:
        raise MediaOperationError("替换时间段无效")
    with tempfile.TemporaryDirectory(prefix="hook-replace-") as temp:
        root = Path(temp); source = root / "source.mp4"; replacement = root / "replacement.mp4"
        before = root / "before.mp4"; middle = root / "middle.mp4"; after = root / "after.mp4"; output = root / "result.mp4"
        await asyncio.gather(download(source_url, source), download(replacement_url, replacement))
        parts: list[Path] = []
        if start > 0.05:
            await run_ffmpeg(["-ss", "0", "-to", str(start), "-i", str(source), "-c:v", "libx264", "-c:a", "aac", str(before)])
            parts.append(before)
        await run_ffmpeg(["-i", str(replacement), "-t", str(end - start), "-c:v", "libx264", "-c:a", "aac", str(middle)])
        parts.append(middle)
        await run_ffmpeg(["-ss", str(end), "-i", str(source), "-c:v", "libx264", "-c:a", "aac", str(after)])
        parts.append(after)
        concat = root / "concat.txt"
        concat.write_text("".join(f"file '{path.as_posix()}'\n" for path in parts), encoding="utf-8")
        await run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-c:a", "aac", str(output)])
        return output.read_bytes()


async def render_animatic_frames(frame_urls: list[str], durations: list[float]) -> bytes:
    if not frame_urls or len(frame_urls) != len(durations):
        raise MediaOperationError("动态预演需要每镜一张clean frame和对应时长")
    if any(duration < 4 or duration > 15 for duration in durations):
        raise MediaOperationError("动态预演镜头时长必须为4-15秒")
    with tempfile.TemporaryDirectory(prefix="hook-animatic-") as temp:
        root = Path(temp)
        frames = []
        for index, url in enumerate(frame_urls):
            suffix = Path(urlsplit(url).path).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                suffix = ".png"
            frames.append(root / f"frame-{index:03d}{suffix}")
        await asyncio.gather(*(download(url, target, max_bytes=30 * 1024 * 1024) for url, target in zip(frame_urls, frames)))
        clips: list[Path] = []
        for index, (frame, duration) in enumerate(zip(frames, durations)):
            clip = root / f"clip-{index:03d}.mp4"
            await run_ffmpeg([
                "-loop", "1", "-t", f"{duration:.3f}", "-i", str(frame),
                "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
                "-r", "30", "-c:v", "libx264", "-an", str(clip),
            ])
            clips.append(clip)
        concat = root / "animatic.txt"
        concat.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
        output = root / "animatic.mp4"
        await run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c", "copy", "-movflags", "+faststart", str(output),
        ])
        return output.read_bytes()
