import asyncio

import pytest

from app.queues import QueueManager, TenantFairQueue
from app.services.production import ProductionManager


def test_tenant_fair_queue_rotates_between_customers():
 async def run():
    queue = TenantFairQueue[str]()
    for task_id, tenant_id in (
        ("a-1", "client-a"), ("a-2", "client-a"), ("a-3", "client-a"),
        ("b-1", "client-b"), ("b-2", "client-b"),
    ):
        await queue.put(task_id, tenant_id)
    assert await queue.positions() == {"a-1": 1, "b-1": 2, "a-2": 3, "b-2": 4, "a-3": 5}
    seen = []
    for _ in range(5):
        seen.append(await queue.get())
        await queue.task_done()
    await queue.join()
    assert seen == ["a-1", "b-1", "a-2", "b-2", "a-3"]
 async def stop_probe():
    queue = TenantFairQueue[str]()
    await queue.put(None)
    assert await queue.get() is None
    await queue.task_done()
    await queue.join()
 asyncio.run(run())
 asyncio.run(stop_probe())


def test_batch_variants_use_one_slot_per_task_and_leave_room_for_another_customer():
 async def run():
    slots = asyncio.Semaphore(2)
    active = {"client-a": 0, "client-b": 0}
    peak = {"client-a": 0, "client-b": 0, "global": 0}
    order = []

    def generator(client_id, delay):
        async def generate(variant):
            async with slots:
                active[client_id] += 1
                peak[client_id] = max(peak[client_id], active[client_id])
                peak["global"] = max(peak["global"], sum(active.values()))
                order.append((client_id, variant, "start"))
                await asyncio.sleep(delay)
                order.append((client_id, variant, "end"))
                active[client_id] -= 1
                return {"client": client_id, "variant": variant}
        return generate

    a, b = await asyncio.gather(
        ProductionManager._run_batch_variants(3, generator("client-a", 0.02)),
        ProductionManager._run_batch_variants(1, generator("client-b", 0.01)),
    )
    assert len(a) == 3 and len(b) == 1
    assert peak == {"client-a": 1, "client-b": 1, "global": 2}
    assert order.index(("client-b", 0, "start")) < order.index(("client-a", 1, "start"))
 asyncio.run(run())


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
