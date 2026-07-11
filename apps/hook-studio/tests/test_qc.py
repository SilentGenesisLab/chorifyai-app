import asyncio

from app.qc import VideoPostflightQC, evaluate_video_probe


def test_qc_requires_vertical_duration_and_audio():
    result = evaluate_video_probe({"format": {"duration": "4.4"}, "streams": [{"codec_type": "video", "width": 720, "height": 1280}, {"codec_type": "audio", "codec_name": "aac"}]})
    assert result.passed


def test_qc_accepts_full_single_shot_range_and_rejects_overflow():
    streams = [{"codec_type": "video", "width": 720, "height": 1280}, {"codec_type": "audio", "codec_name": "aac"}]
    assert evaluate_video_probe({"duration": 14.8, "streams": streams}).passed
    overflow = evaluate_video_probe({"duration": 16.2, "streams": streams})
    assert not overflow.passed
    assert next(item for item in overflow.checks if item.id == "duration").status == "fail"


def test_qc_rejects_silent_clip():
    result = evaluate_video_probe({"duration": 4, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    assert not result.passed
    assert next(item for item in result.checks if item.id == "native-audio").status == "fail"


def test_qc_probe_failure_is_observable_not_exception():
    async def run():
        async def broken(_):
            raise RuntimeError("offline")
        result = await VideoPostflightQC(broken).run("https://cdn/v.mp4")
        assert not result.passed
        assert result.checks[0].id == "media-probe"
    asyncio.run(run())
