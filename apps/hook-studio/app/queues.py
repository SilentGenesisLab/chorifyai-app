from __future__ import annotations

import asyncio
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, TypeVar


T = TypeVar("T")


class TenantFairQueue(Generic[T]):
    """Async round-robin queue that gives each tenant one turn at a time."""

    def __init__(self) -> None:
        self._lanes: dict[str, deque[T]] = {}
        self._rotation: deque[str] = deque()
        self._active: set[str] = set()
        self._stops = 0
        self._unfinished = 0
        self._condition = asyncio.Condition()
        self._finished = asyncio.Event()
        self._finished.set()

    async def put(self, item: T | None, tenant_id: str | None = None) -> None:
        async with self._condition:
            if item is None:
                self._stops += 1
            else:
                tenant = (tenant_id or "default").strip() or "default"
                lane = self._lanes.setdefault(tenant, deque())
                lane.append(item)
                if tenant not in self._active:
                    self._rotation.append(tenant)
                    self._active.add(tenant)
            self._unfinished += 1
            self._finished.clear()
            self._condition.notify()

    async def get(self) -> T | None:
        async with self._condition:
            while not self._rotation and self._stops == 0:
                await self._condition.wait()
            if not self._rotation and self._stops:
                self._stops -= 1
                return None
            tenant = self._rotation.popleft()
            lane = self._lanes[tenant]
            item = lane.popleft()
            if lane:
                self._rotation.append(tenant)
            else:
                del self._lanes[tenant]
                self._active.discard(tenant)
            return item

    async def task_done(self) -> None:
        async with self._condition:
            if self._unfinished <= 0:
                raise ValueError("task_done called too many times")
            self._unfinished -= 1
            if self._unfinished == 0:
                self._finished.set()

    async def join(self) -> None:
        await self._finished.wait()

    def _ordered_items(self) -> list[T]:
        lanes = {tenant: deque(items) for tenant, items in self._lanes.items()}
        rotation = deque(self._rotation)
        ordered: list[T] = []
        while rotation:
            tenant = rotation.popleft()
            lane = lanes[tenant]
            ordered.append(lane.popleft())
            if lane:
                rotation.append(tenant)
        return ordered

    async def positions(self) -> dict[T, int]:
        async with self._condition:
            return {item: index + 1 for index, item in enumerate(self._ordered_items())}

    async def position(self, item: T) -> int | None:
        return (await self.positions()).get(item)


@dataclass(frozen=True)
class QueueSnapshot:
    name: str
    queued: int
    running: int
    concurrency: int
    position: int | None
    eta_seconds: int | None


class GenerationQueue:
    def __init__(self, name: str, concurrency: int, handler: Callable[[str], Awaitable[None]], *, fallback_eta_seconds: int):
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.name = name
        self.concurrency = concurrency
        self.handler = handler
        self.fallback_eta_seconds = fallback_eta_seconds
        self._queue: TenantFairQueue[str] = TenantFairQueue()
        self._pending: list[str] = []
        self._running: set[str] = set()
        self._durations: deque[float] = deque(maxlen=20)
        self._workers: list[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._workers:
            return
        self._workers = [asyncio.create_task(self._worker(), name=f"hook-{self.name}-{index}") for index in range(self.concurrency)]

    async def stop(self) -> None:
        workers, self._workers = self._workers, []
        for _ in workers:
            await self._queue.put(None)
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    async def enqueue(self, job_id: str, *, tenant_id: str = "default") -> None:
        async with self._lock:
            if job_id in self._pending or job_id in self._running:
                return
            self._pending.append(job_id)
        await self._queue.put(job_id, tenant_id)

    async def _worker(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            job_id = await self._queue.get()
            if job_id is None:
                await self._queue.task_done()
                return
            started = loop.time()
            async with self._lock:
                if job_id in self._pending:
                    self._pending.remove(job_id)
                self._running.add(job_id)
            succeeded = False
            try:
                await self.handler(job_id)
                succeeded = True
            except Exception:
                # The durable job handler records failure; one bad job must not kill a worker.
                succeeded = False
            finally:
                async with self._lock:
                    self._running.discard(job_id)
                    if succeeded:
                        self._durations.append(loop.time() - started)
                await self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    async def snapshot(self, job_id: str | None = None) -> QueueSnapshot:
        async with self._lock:
            sample = statistics.median(self._durations) if self._durations else self.fallback_eta_seconds
        position = await self._queue.position(job_id) if job_id else None
        async with self._lock:
            eta = None if position is None else max(1, int(((position - 1) // self.concurrency + 1) * sample))
            return QueueSnapshot(self.name, len(self._pending), len(self._running), self.concurrency, position, eta)


class QueueManager:
    """Owns physically independent image/video worker pools."""

    def __init__(self, handler: Callable[[str], Awaitable[None]], *, image_concurrency: int = 2, video_concurrency: int = 2):
        self.image = GenerationQueue("image", image_concurrency, handler, fallback_eta_seconds=90)
        self.video = GenerationQueue("video", video_concurrency, handler, fallback_eta_seconds=300)

    async def start(self) -> None:
        await asyncio.gather(self.image.start(), self.video.start())

    async def stop(self) -> None:
        await asyncio.gather(self.image.stop(), self.video.stop())

    async def enqueue(self, mode: str, job_id: str, *, tenant_id: str = "default") -> None:
        await self.for_mode(mode).enqueue(job_id, tenant_id=tenant_id)

    def for_mode(self, mode: str) -> GenerationQueue:
        if mode == "image":
            return self.image
        if mode == "video":
            return self.video
        raise ValueError(f"unsupported mode: {mode}")

    async def recover(self, repository: object) -> int:
        """Requeue durable queued/running jobs; repository owns state transition."""
        recover = getattr(repository, "recover_incomplete_jobs")
        jobs = await recover()
        for job in jobs:
            mode = job["mode"] if isinstance(job, dict) else job.mode
            job_id = job["id"] if isinstance(job, dict) else job.id
            tenant_id = job.get("client_id", "default") if isinstance(job, dict) else getattr(job, "client_id", "default")
            await self.enqueue(mode, job_id, tenant_id=tenant_id)
        return len(jobs)
