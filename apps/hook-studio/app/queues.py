from __future__ import annotations

import asyncio
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable


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
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
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

    async def enqueue(self, job_id: str) -> None:
        async with self._lock:
            if job_id in self._pending or job_id in self._running:
                return
            self._pending.append(job_id)
        await self._queue.put(job_id)

    async def _worker(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            job_id = await self._queue.get()
            if job_id is None:
                self._queue.task_done()
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
                self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    async def snapshot(self, job_id: str | None = None) -> QueueSnapshot:
        async with self._lock:
            position = self._pending.index(job_id) + 1 if job_id in self._pending else None
            sample = statistics.median(self._durations) if self._durations else self.fallback_eta_seconds
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

    async def enqueue(self, mode: str, job_id: str) -> None:
        await self.for_mode(mode).enqueue(job_id)

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
            await self.enqueue(mode, job_id)
        return len(jobs)
