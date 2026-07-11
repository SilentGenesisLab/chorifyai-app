from __future__ import annotations

import asyncio
import functools
import http.server
import json
import shutil
import subprocess
import threading

import pytest

from app.services.media_ops import render_animatic_frames


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="requires FFmpeg")
def test_real_ffmpeg_animatic_accepts_png_and_jpeg_and_keeps_duration(tmp_path):
    png = tmp_path / "first.png"
    jpg = tmp_path / "second.jpg"
    subprocess.run([
        shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", str(png),
    ], check=True)
    subprocess.run([
        shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=64x64", "-frames:v", "1", str(jpg),
    ], check=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        content = asyncio.run(render_animatic_frames([f"{base}/first.png", f"{base}/second.jpg"], [4, 5]))
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()
    output = tmp_path / "animatic.mp4"; output.write_bytes(content)
    probe = subprocess.run([
        shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(output),
    ], check=True, capture_output=True, text=True)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert 8.9 <= duration <= 9.2
