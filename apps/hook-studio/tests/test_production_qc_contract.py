from __future__ import annotations

import asyncio

import pytest

from app.services.production import ProductionError, ProductionManager


class ProbeProvider:
    def __init__(self, probe):
        self.probe = probe

    async def probe_media(self, source_uri: str, *, request_id: str):
        return self.probe


def _manager(probe):
    manager = ProductionManager.__new__(ProductionManager)
    manager.provider = ProbeProvider(probe)
    return manager


def test_production_qc_returns_structured_vertical_audio_evidence():
    probe = {
        "duration": 8.1,
        "streams": [
            {"codec_type": "video", "width": 720, "height": 1280},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    result = asyncio.run(_manager(probe)._probe_video("https://cdn/shot.mp4", request_id="shot:qc"))
    assert result["passed"] is True
    assert {item["id"] for item in result["checks"]} >= {
        "playable-video", "duration", "ratio", "native-audio",
    }


@pytest.mark.parametrize("probe,failed_check", [
    ({"duration": 8, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]}, "native-audio"),
    ({"duration": 8, "streams": [{"codec_type": "video", "width": 1280, "height": 720}, {"codec_type": "audio"}]}, "ratio"),
    ({"duration": 18, "streams": [{"codec_type": "video", "width": 720, "height": 1280}, {"codec_type": "audio"}]}, "duration"),
])
def test_production_qc_blocks_invalid_single_shot_before_delivery(probe, failed_check):
    with pytest.raises(ProductionError, match=failed_check):
        asyncio.run(_manager(probe)._probe_video("https://cdn/invalid.mp4", request_id="shot:qc"))


def test_assembled_video_accepts_full_mvp_duration_range():
    probe = {
        "duration": 59.8,
        "streams": [
            {"codec_type": "video", "width": 720, "height": 1280},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    result = asyncio.run(_manager(probe)._probe_video(
        "https://cdn/final.mp4", request_id="task:assemble:qc", max_duration=60.5,
    ))
    assert result["passed"] is True
