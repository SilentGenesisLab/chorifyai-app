import asyncio
from pathlib import Path

import pytest

from app.providers.kernel import ProviderResult
from app.qc import VideoPostflightQC
from app.services.generation import GenerationCommand, GenerationService
from app.skill_policy import VideoSkillPolicy


class Repo:
    def __init__(self): self.jobs = {}
    async def create_job(self, values): self.jobs[values["id"]] = dict(values); return dict(values)
    async def get_job(self, job_id): return self.jobs.get(job_id)
    async def update_job(self, job_id, values): self.jobs[job_id].update(values)


class Quota:
    def __init__(self): self.calls = []
    def reserve_video(self, client, limit): self.calls.append(("reserve", client, limit))
    def mark_succeeded(self, client, limit, **kwargs): self.calls.append(("success", client, limit))
    def release_failed(self, client, limit, **kwargs): self.calls.append(("release", client, limit))


class Events:
    def __init__(self): self.items = []
    def write(self, event): self.items.append(event); return len(self.items)


class Provider:
    async def submit_video(self, **kwargs): return ProviderResult("submitted", submit_id="s1")
    async def poll_video(self, *args, **kwargs): return ProviderResult("success", "https://cdn/v.mp4", "s1")


class Queues:
    def __init__(self): self.items = []
    async def enqueue(self, mode, job_id): self.items.append((mode, job_id))


def test_video_reservation_and_postflight_success():
 async def run():
    repo, quota, events = Repo(), Quota(), Events()
    policy = VideoSkillPolicy.from_file(Path(__file__).parents[1] / "config" / "skill-policy-v1.yaml")
    async def probe(_): return {"duration": 4.2, "streams": [{"codec_type": "video", "width": 720, "height": 1280}, {"codec_type": "audio"}]}
    service = GenerationService(repo, Provider(), quota, events, policy, VideoPostflightQC(probe), poll_interval=0, poll_timeout=1)
    queues = Queues(); service.bind_queues(queues)
    job = await service.submit(GenerationCommand(client_id="c1", client_video_limit=20, mode="video", preset_id="pain-point", template_version="1.0.0", prompt_user="产品", prompt_final="美区厨房里，当用户按下按钮，随后产品打开，同时保留原生环境音和动作音，不出现水印。"))
    await service.process(job["id"])
    assert repo.jobs[job["id"]]["status"] == "succeeded"
    assert [call[0] for call in quota.calls] == ["reserve", "success"]
    assert len(events.items) == 2
 asyncio.run(run())


def test_silent_video_releases_quota():
 async def run():
    repo, quota, events = Repo(), Quota(), Events()
    policy = VideoSkillPolicy.from_file(Path(__file__).parents[1] / "config" / "skill-policy-v1.yaml")
    async def probe(_): return {"duration": 4.2, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]}
    service = GenerationService(repo, Provider(), quota, events, policy, VideoPostflightQC(probe), poll_interval=0, poll_timeout=1)
    service.bind_queues(Queues())
    job = await service.submit(GenerationCommand(client_id="c1", mode="video", preset_id="pain-point", template_version="1", prompt_user="产品", prompt_final="美区厨房里，当用户按下按钮，随后产品打开，同时保留原生环境音和动作音，不出现水印。"))
    await service.process(job["id"])
    assert repo.jobs[job["id"]]["status"] == "failed"
    assert quota.calls[-1][0] == "release"
 asyncio.run(run())
