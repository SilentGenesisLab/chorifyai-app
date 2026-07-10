from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.providers.kernel import ProviderError, ProviderResult
from app.qc import VideoPostflightQC
from app.skill_policy import SkillGateBlocked, VideoSkillPolicy


class Repository(Protocol):
    async def create_job(self, values: dict[str, Any]) -> dict[str, Any]: ...
    async def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    async def update_job(self, job_id: str, values: dict[str, Any]) -> None: ...


class Quota(Protocol):
    def reserve_video(self, client_id: str, client_limit: int) -> Any: ...
    def mark_succeeded(self, client_id: str, client_limit: int, **kwargs: Any) -> Any: ...
    def release_failed(self, client_id: str, client_limit: int, **kwargs: Any) -> Any: ...


class Events(Protocol):
    def write(self, event: Any) -> int: ...


@dataclass(frozen=True)
class GenerationCommand:
    client_id: str
    mode: str
    preset_id: str
    template_version: str
    prompt_user: str
    prompt_final: str
    duration: int = 4
    reference_urls: list[str] = field(default_factory=list)
    slot_manifest: list[dict[str, Any]] = field(default_factory=list)
    client_video_limit: int = 100


class GenerationFailure(RuntimeError):
    def __init__(self, code: str, message: str, request_id: str):
        self.code = code
        self.request_id = request_id
        super().__init__(message)


class GenerationService:
    def __init__(self, repository: Repository, provider: object, quota: Quota, events: Events, policy: VideoSkillPolicy, qc: VideoPostflightQC, *, poll_interval: float = 3, poll_timeout: float = 900):
        self.repository = repository
        self.provider = provider
        self.quota = quota
        self.events = events
        self.policy = policy
        self.qc = qc
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.queues: Any = None

    @staticmethod
    async def _call(value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    async def _quota(self, operation: str, client_id: str, limit: int, **kwargs: Any) -> Any:
        method = getattr(self.quota, operation)
        return await self._call(method(client_id, limit, **kwargs))

    async def _event(self, action: str, job: dict[str, Any], **overrides: Any) -> None:
        try:
            from app.models import EventAction, EventRecord, Mode

            values = {
                "ts": datetime.now(timezone.utc), "access_code": job["client_id"],
                "mode": Mode(job["mode"]), "preset_id": job["preset_id"],
                "template_version": job["template_version"], "prompt_user": job["prompt_user"],
                "prompt_final": job["prompt_final"], "params": {"duration": job.get("duration", 4)},
                "model": "gpt-image-2" if job["mode"] == "image" else "seedance2.0fast_vip",
                "result_url": job.get("result_url"), "latency_ms": job.get("latency_ms"),
                "cost_units": 1 if action == "generate" and job["mode"] == "video" and job.get("result_url") else 0,
                "action": EventAction(action), "job_id": job["id"], "client_id": job["client_id"],
                "queue_name": job["mode"], "queue_wait_ms": job.get("queue_wait_ms"),
                "provider_attempt": job.get("provider_attempt"), "skill_trace": job.get("skill_trace"),
                "error_code": job.get("error_code"),
            }
            values.update(overrides)
            writer = getattr(self.events, "write")
            await self._call(writer(EventRecord(**values)))
        except Exception:
            # Event write failures are operationally important and must fail the caller.
            raise

    def bind_queues(self, queues: object) -> None:
        self.queues = queues

    async def submit(self, command: GenerationCommand) -> dict[str, Any]:
        if command.mode not in {"image", "video"}:
            raise GenerationFailure("INPUT_INVALID", "生成模式无效", uuid4().hex)
        job_id = uuid4().hex
        trace: dict[str, Any] = {}
        reservation_day: str | None = None
        if command.mode == "video":
            try:
                trace = self.policy.require(prompt=command.prompt_final, duration=command.duration, ratio="9:16", reference_urls=command.reference_urls, slot_manifest=command.slot_manifest).as_dict()
            except SkillGateBlocked as exc:
                blocked = {**asdict(command), "id": job_id, "model": "seedance2.0fast_vip", "skill_trace": exc.trace.as_dict(), "error_code": exc.code}
                await self._event("generate", blocked)
                raise GenerationFailure(exc.code, str(exc), job_id) from exc
            reservation = await self._quota("reserve_video", command.client_id, command.client_video_limit)
            reservation_day = getattr(reservation, "day_cn", None)
        values = {**asdict(command), "reservation_day": reservation_day, "id": job_id, "status": "queued", "queue_name": command.mode, "skill_trace": trace, "retry_count": 0, "queued_at": datetime.now(timezone.utc).isoformat(), "model": "gpt-image-2" if command.mode == "image" else "seedance2.0fast_vip"}
        try:
            job = await self.repository.create_job(values)
            await self._event("generate", values)
            if self.queues is None:
                raise RuntimeError("generation queues are not bound")
            await self.queues.enqueue(command.mode, job_id)
        except Exception:
            if command.mode == "video":
                await self._quota("release_failed", command.client_id, command.client_video_limit)
            raise
        return job

    async def process(self, job_id: str) -> None:
        job = await self.repository.get_job(job_id)
        if not job or job.get("status") not in {"queued", "running"}:
            return
        mode = job["mode"]
        client_id = job["client_id"]
        started = time.monotonic()
        started_at = datetime.now(timezone.utc)
        try:
            queued_at = datetime.fromisoformat(str(job["queued_at"]).replace("Z", "+00:00"))
            queue_wait_ms = max(0, int((started_at - queued_at).total_seconds() * 1000))
        except (KeyError, TypeError, ValueError):
            queue_wait_ms = None
        await self.repository.update_job(job_id, {"status": "running", "started_at": started_at.isoformat()})
        try:
            if mode == "image":
                result = await self.provider.generate_image(prompt=job["prompt_final"], reference_urls=job.get("reference_urls", []), request_id=job_id, metadata={"preset_id": job["preset_id"], "template_version": job["template_version"]})
            else:
                result = await self._generate_video(job)
            latency_ms = int((time.monotonic() - started) * 1000)
            done = {**job, "status": "succeeded", "result_url": result.result_url, "provider_job_id": result.submit_id, "result_meta": result.trace, "latency_ms": latency_ms, "queue_wait_ms": queue_wait_ms, "provider_attempt": int(result.trace.get("attempts", 1)), "finished_at": datetime.now(timezone.utc).isoformat()}
            await self.repository.update_job(job_id, done)
            if mode == "video":
                await self._quota("mark_succeeded", client_id, int(job.get("client_video_limit", 100)), reservation_day=job.get("reservation_day"))
            await self._event("generate", done)
        except Exception as exc:
            code = getattr(exc, "code", "INTERNAL_ERROR")
            failed = {**job, "status": "failed", "error_code": code, "error_message": str(exc), "finished_at": datetime.now(timezone.utc).isoformat()}
            await self.repository.update_job(job_id, failed)
            if mode == "video":
                await self._quota("release_failed", client_id, int(job.get("client_video_limit", 100)), reservation_day=job.get("reservation_day"))
            await self._event("generate", failed)

    async def _generate_video(self, job: dict[str, Any]) -> ProviderResult:
        result = await self.provider.submit_video(prompt=job["prompt_final"], image_urls=job.get("reference_urls", []), duration=int(job.get("duration", 4)), request_id=job["id"], metadata={"preset_id": job["preset_id"], "template_version": job["template_version"], "skill_trace": job.get("skill_trace", {})})
        submit_trace = dict(result.trace)
        await self.repository.update_job(job["id"], {"provider_job_id": result.submit_id, "provider_status": result.status})
        if result.status == "failed":
            raise ProviderError(result.failure_reason or "视频生成被Provider拒绝")
        deadline = time.monotonic() + self.poll_timeout
        while result.status not in {"success", "failed", "cancelled"}:
            if time.monotonic() >= deadline:
                error = TimeoutError("视频生成轮询超时；已保存任务编号，可继续查询，不会重复提交")
                error.code = "PROVIDER_TIMEOUT"  # type: ignore[attr-defined]
                raise error
            await asyncio.sleep(self.poll_interval)
            result = await self.provider.poll_video(result.submit_id, request_id=job["id"])
        if result.status != "success" or not result.result_url:
            raise ProviderError(result.failure_reason or f"视频任务状态为{result.status}")
        qc = await self.qc.run(result.result_url)
        await self.repository.update_job(job["id"], {"result_meta": {"provider": result.trace, "qc": qc.as_dict()}})
        if not qc.passed:
            error = ValueError("成片技术安检未通过，未计为成功")
            error.code = "RESULT_INVALID"  # type: ignore[attr-defined]
            raise error
        return ProviderResult(result.status, result.result_url, result.submit_id, result.local_path, trace={"attempts": int(submit_trace.get("attempts", 1)), "submit": submit_trace, "poll": result.trace, "qc": qc.as_dict()})


class SQLiteJobRepository:
    """Small adapter over app.db.Database; JSON decoding happens at this boundary."""

    def __init__(self, db: Any):
        self.db = db

    @staticmethod
    def _decode(row: Any) -> dict[str, Any]:
        value = dict(row)
        params = json.loads(value.pop("params_json", "{}") or "{}")
        value.update(params)
        value["skill_trace"] = json.loads(value.pop("skill_trace_json", "null") or "null")
        value["result_meta"] = json.loads(value.pop("result_meta_json", "null") or "null")
        return value

    async def create_job(self, values: dict[str, Any]) -> dict[str, Any]:
        params = {key: values[key] for key in ("duration", "reference_urls", "slot_manifest", "client_video_limit", "reservation_day") if key in values}
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT INTO jobs(id,client_id,mode,preset_id,template_version,prompt_user,prompt_final,params_json,model,status,queue_name,skill_trace_json,retry_count,queued_at,parent_job_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (values["id"], values["client_id"], values["mode"], values["preset_id"], values["template_version"], values["prompt_user"], values["prompt_final"], json.dumps(params, ensure_ascii=False), values["model"], "queued", values["queue_name"], json.dumps(values.get("skill_trace") or {}, ensure_ascii=False), 0, values["queued_at"], values.get("parent_job_id")),
            )
        return dict(values)

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._decode(row) if row else None

    async def update_job(self, job_id: str, values: dict[str, Any]) -> None:
        columns: dict[str, Any] = {}
        for key in ("status", "provider_job_id", "result_url", "error_code", "error_message", "retry_count", "started_at", "finished_at", "deleted_at"):
            if key in values:
                columns[key] = values[key]
        if "skill_trace" in values:
            columns["skill_trace_json"] = json.dumps(values["skill_trace"], ensure_ascii=False)
        if "result_meta" in values:
            columns["result_meta_json"] = json.dumps(values["result_meta"], ensure_ascii=False)
        if not columns:
            return
        sql = "UPDATE jobs SET " + ",".join(f"{name}=?" for name in columns) + " WHERE id=?"
        with self.db.transaction(immediate=True) as conn:
            conn.execute(sql, (*columns.values(), job_id))

    async def recover_incomplete_jobs(self) -> list[dict[str, Any]]:
        with self.db.transaction(immediate=True) as conn:
            conn.execute("UPDATE jobs SET status='queued', started_at=NULL WHERE status='running'")
            rows = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY queued_at").fetchall()
        return [self._decode(row) for row in rows]

    async def list_jobs(self, client_id: str, *, gallery_only: bool = False) -> list[dict[str, Any]]:
        clause = " AND status='succeeded'" if gallery_only else ""
        with self.db.transaction() as conn:
            rows = conn.execute(f"SELECT * FROM jobs WHERE client_id=? AND deleted_at IS NULL{clause} ORDER BY queued_at DESC", (client_id,)).fetchall()
        return [self._decode(row) for row in rows]
