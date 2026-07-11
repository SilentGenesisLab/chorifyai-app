import asyncio
import json

import httpx
import pytest

from app.providers.kernel import KernelProvider, ProviderRejected, ProviderTimeout


def test_submit_then_poll_same_video_id():
 async def run():
    seen = []
    async def handler(request):
        seen.append(request)
        if request.url.path.endswith("/videos/generate"):
            return httpx.Response(200, json={"submit_id": "s1", "status": "submitted", "provider_trace": {}})
        return httpx.Response(200, json={"submit_id": "s1", "status": "success", "video_url": "https://cdn/v.mp4", "raw": {}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KernelProvider("http://kernel", "secret", client=client)
        submit = await provider.submit_video(prompt="p", image_urls=[], duration=4, request_id="j1")
        done = await provider.poll_video(submit.submit_id, request_id="j1")
    assert done.result_url.endswith("v.mp4")
    assert all(request.headers["authorization"] == "Bearer secret" for request in seen)
    assert all("run_id" not in request.url.params for request in seen)
    assert "run_id" not in seen[0].read().decode()
 asyncio.run(run())


def test_timeout_gets_exactly_one_retry():
 async def run():
    calls = 0
    async def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("late", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KernelProvider("http://kernel", None, client=client)
        with pytest.raises(ProviderTimeout):
            await provider.generate_image(prompt="p", reference_urls=[], request_id="j1")
    assert calls == 2
 asyncio.run(run())


def test_submit_video_forwards_reference_videos():
 async def run():
    payload = {}

    async def handler(request):
        payload.update(json.loads((await request.aread()).decode()))
        return httpx.Response(200, json={"submit_id": "s2", "status": "submitted", "provider_trace": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KernelProvider("http://kernel", "secret", client=client)
        await provider.submit_video(
            prompt="只参考视频1的动作",
            image_urls=["https://cdn/product.jpg"],
            video_urls=["https://cdn/reference.mp4"],
            duration=8,
            request_id="j2",
        )
    assert payload["video_urls"] == ["https://cdn/reference.mp4"]
    assert payload["image_urls"] == ["https://cdn/product.jpg"]
    assert payload["external_ref"] == "hook-studio:j2"
    assert payload["metadata"]["generation_mode"] == "multimodal"

 asyncio.run(run())


def test_submit_video_rejects_unverified_mode_before_network():
 async def run():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"submit_id": "unexpected"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KernelProvider("http://kernel", None, client=client)
        with pytest.raises(ProviderRejected, match="能力探针"):
            await provider.submit_video(
                prompt="p", image_urls=["https://cdn/start.jpg"], duration=8,
                request_id="mode-1", generation_mode="first_last",
            )
    assert calls == 0

 asyncio.run(run())


@pytest.mark.parametrize("duration", [3, 16])
def test_submit_video_enforces_single_shot_duration(duration):
 async def run():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        provider = KernelProvider("http://kernel", None, client=client)
        with pytest.raises(ProviderRejected, match="4-15秒"):
            await provider.submit_video(prompt="p", image_urls=[], duration=duration, request_id="duration-1")

 asyncio.run(run())


def test_stream_attachment_uploads_as_multipart():
 async def run():
    seen_body = b""

    async def handler(request):
        nonlocal seen_body
        seen_body = await request.aread()
        return httpx.Response(200, json={"uri": "https://cdn/reference.mp4"})

    async def chunks():
        yield b"video-"
        yield b"bytes"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KernelProvider("http://kernel", None, client=client)
        uri = await provider.upload_attachment(
            "../reference.mp4",
            chunks(),
            "video/mp4",
            request_id="upload-1",
            max_bytes=32,
        )
    assert uri == "https://cdn/reference.mp4"
    assert b'reference.mp4' in seen_body
    assert b'video/mp4' in seen_body
    assert b'video-bytes' in seen_body
    assert b'../reference.mp4' not in seen_body

 asyncio.run(run())


def test_stream_attachment_enforces_limit_before_request():
 async def run():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"uri": "https://cdn/file"})

    async def chunks():
        yield b"1234"
        yield b"5678"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KernelProvider("http://kernel", None, client=client)
        with pytest.raises(ProviderRejected, match="附件不能超过"):
            await provider.upload_attachment("large.mp4", chunks(), "video/mp4", max_bytes=7)
    assert calls == 0

 asyncio.run(run())


def test_understand_transcode_and_extract_frame_contracts():
 async def run():
    requests = []

    async def handler(request):
        requests.append((request.url.path, json.loads((await request.aread()).decode())))
        if request.url.path.endswith("/understand/evaluate"):
            return httpx.Response(200, json={"analysis": {"shots": [{"id": "S1"}]}})
        if request.url.path.endswith("/media/transcode"):
            return httpx.Response(200, json={"video_url": "https://cdn/final.mp4", "source_count": 2})
        return httpx.Response(200, json={"frame_url": "https://cdn/frame.jpg"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KernelProvider("http://kernel", "secret", client=client)
        analysis = await provider.understand(text="逆向分析", video_urls=["https://cdn/ref.mp4"], request_id="u1")
        transcoded = await provider.transcode(["https://cdn/a.mp4", "https://cdn/b.mp4"], request_id="t1")
        frame = await provider.extract_frame("https://cdn/final.mp4", offset_from_end=1.25, request_id="f1")

    assert analysis["shots"][0]["id"] == "S1"
    assert transcoded.result_url == "https://cdn/final.mp4"
    assert frame.result_url == "https://cdn/frame.jpg"
    by_path = {path: payload for path, payload in requests}
    assert by_path["/capabilities/v1/understand/evaluate"]["video_urls"] == ["https://cdn/ref.mp4"]
    assert by_path["/capabilities/v1/media/transcode"]["source_uris"] == ["https://cdn/a.mp4", "https://cdn/b.mp4"]
    assert by_path["/capabilities/v1/media/extract-frame"]["offset_from_end"] == 1.25

 asyncio.run(run())
