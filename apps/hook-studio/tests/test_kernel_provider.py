import asyncio
import httpx
import pytest

from app.providers.kernel import KernelProvider, ProviderTimeout


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
