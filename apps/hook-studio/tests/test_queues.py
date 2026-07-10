import asyncio

import pytest

from app.queues import QueueManager


def test_image_and_video_have_independent_concurrency():
 async def run():
    active = {"image": 0, "video": 0}
    peak = {"image": 0, "video": 0}
    async def handler(job_id):
        mode = job_id.split("-")[0]
        active[mode] += 1
        peak[mode] = max(peak[mode], active[mode])
        await asyncio.sleep(0.02)
        active[mode] -= 1
    queues = QueueManager(handler, image_concurrency=1, video_concurrency=2)
    await queues.start()
    for job in ("image-1", "image-2", "video-1", "video-2"):
        await queues.enqueue(job.split("-")[0], job)
    await asyncio.gather(queues.image.join(), queues.video.join())
    await queues.stop()
    assert peak == {"image": 1, "video": 2}
 asyncio.run(run())


def test_worker_survives_handler_failure():
 async def run():
    seen = []
    async def handler(job_id):
        seen.append(job_id)
        if job_id == "image-bad":
            raise RuntimeError("bad")
    queues = QueueManager(handler, image_concurrency=1, video_concurrency=1)
    await queues.start()
    await queues.enqueue("image", "image-bad")
    await queues.enqueue("image", "image-good")
    await queues.image.join()
    await queues.stop()
    assert seen == ["image-bad", "image-good"]
 asyncio.run(run())
