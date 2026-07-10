from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class QCCheck:
    id: str
    status: str
    message: str = ""
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True)
class QCResult:
    passed: bool
    checks: list[QCCheck]
    probe: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dimensions(probe: dict[str, Any]) -> tuple[int, int]:
    video = probe.get("video") if isinstance(probe.get("video"), dict) else {}
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    return int(video.get("width") or stream.get("width") or probe.get("width") or 0), int(video.get("height") or stream.get("height") or probe.get("height") or 0)


def evaluate_video_probe(probe: dict[str, Any], *, min_duration: float = 3.8, max_duration: float = 5.5, ratio_tolerance: float = 0.04) -> QCResult:
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    width, height = _dimensions(probe)
    duration = _number(probe.get("duration") or (probe.get("format") or {}).get("duration"))
    has_video = bool(width and height) or any(item.get("codec_type") == "video" for item in streams)
    has_audio = bool((probe.get("audio") or {}).get("codec_name")) or any(item.get("codec_type") == "audio" for item in streams)
    ratio = width / height if height else 0
    checks = [
        QCCheck("result-url", "pass", "产物URL已由调用方验证"),
        QCCheck("playable-video", "pass" if has_video else "fail", "成片必须含可播放视频流", {"width": width, "height": height}),
        QCCheck("duration", "pass" if min_duration <= duration <= max_duration else "fail", "成片时长必须为4-5秒", {"duration": duration}),
        QCCheck("ratio", "pass" if height > width and abs(ratio - 9 / 16) <= ratio_tolerance else "fail", "成片必须为9:16竖屏", {"ratio": ratio}),
        QCCheck("native-audio", "pass" if has_audio else "fail", "成片缺少原生环境音或动作音轨"),
    ]
    return QCResult(all(item.status == "pass" for item in checks), checks, probe)


class VideoPostflightQC:
    def __init__(self, probe: Callable[[str], Awaitable[dict[str, Any]]]):
        self.probe = probe

    async def run(self, result_url: str | None) -> QCResult:
        if not result_url or not result_url.startswith(("http://", "https://")):
            return QCResult(False, [QCCheck("result-url", "fail", "成片URL无效")], {})
        try:
            probe = await self.probe(result_url)
        except Exception as exc:
            return QCResult(False, [QCCheck("media-probe", "fail", "无法验证成片可播放性", {"error": type(exc).__name__})], {})
        return evaluate_video_probe(probe)
