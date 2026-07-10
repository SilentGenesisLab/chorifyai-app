from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.repositories.workspace import WorkspaceConflict, WorkspaceRepository
from app.models import EventAction, EventRecord, Mode
from app.services.analysis import ReferenceAnalysisService
from app.services.audio import AudioReplacementService
from app.services.media_ops import replace_segment_file
from app.services.planning import normalize_plan, planning_prompt, split_duration


TERMINAL = {"succeeded", "failed", "cancelled"}
VIDEO_TOOLS = {"create", "replicate", "batch", "replace", "voice_replace"}


class ProductionError(RuntimeError):
    code = "PRODUCTION_FAILED"


class ProductionManager:
    """Durable task state machine; SQLite is truth and the queue is disposable."""

    def __init__(
        self, repository: WorkspaceRepository, provider: Any, *,
        global_image_limit: int = 1000, global_video_limit: int = 100,
        concurrency: int | None = None, image_concurrency: int = 2,
        video_concurrency: int = 2, poll_interval: float = 20, poll_timeout: float = 7200,
        audio: AudioReplacementService | None = None, events: Any | None = None,
    ):
        self.repository = repository; self.provider = provider
        self.global_image_limit = global_image_limit; self.global_video_limit = global_video_limit
        if concurrency is not None:
            image_concurrency = video_concurrency = concurrency
        self.concurrency = {"image": image_concurrency, "video": video_concurrency}
        self.poll_interval = poll_interval; self.poll_timeout = poll_timeout
        self.audio = audio; self.analysis = ReferenceAnalysisService(provider); self.events = events
        self._queues = {"image": asyncio.Queue(), "video": asyncio.Queue()}
        self._workers: list[asyncio.Task[None]] = []
        self._pending = {"image": set(), "video": set()}
        self._running = {"image": set(), "video": set()}
        self._lock = asyncio.Lock()
        self._planning_lock = asyncio.Semaphore(1)
        self._generation_slots = asyncio.Semaphore(video_concurrency)

    async def start(self) -> None:
        if self._workers: return
        self._workers = [
            asyncio.create_task(self._worker(queue_name), name=f"hook-production-{queue_name}-{index}")
            for queue_name, count in self.concurrency.items()
            for index in range(count)
        ]

    async def stop(self) -> None:
        workers, self._workers = self._workers, []
        for worker in workers:
            queue_name = "image" if "-image-" in worker.get_name() else "video"
            await self._queues[queue_name].put(None)
        if workers: await asyncio.gather(*workers, return_exceptions=True)

    async def recover(self) -> int:
        with self.repository.db.transaction() as conn:
            rows = conn.execute("SELECT id FROM task_runs WHERE status IN ('queued','planning','generating','assembling') AND deleted_at IS NULL").fetchall()
        for row in rows: await self.enqueue(row["id"])
        return len(rows)

    async def enqueue(self, task_id: str) -> None:
        task = self.repository.get_task(task_id)
        if not task:
            return
        queue_name = "image" if task["kind"] == "image" else "video"
        async with self._lock:
            if task_id in self._pending[queue_name] or task_id in self._running[queue_name]: return
            self._pending[queue_name].add(task_id)
        await self._queues[queue_name].put(task_id)

    async def snapshot(self) -> dict[str, int]:
        async with self._lock:
            image_queued, video_queued = len(self._pending["image"]), len(self._pending["video"])
            image_running, video_running = len(self._running["image"]), len(self._running["video"])
        with self.repository.db.transaction() as conn:
            counts = {row["status"]: row["n"] for row in conn.execute("SELECT status,COUNT(*) n FROM task_runs WHERE deleted_at IS NULL GROUP BY status")}
        return {
            "queued": image_queued + video_queued, "running": image_running + video_running,
            "image_queued": image_queued, "video_queued": video_queued,
            "image_running": image_running, "video_running": video_running,
            "waiting_approval": int(counts.get("waiting_approval", 0)),
            "succeeded": int(counts.get("succeeded", 0)), "failed": int(counts.get("failed", 0)),
            "concurrency": self.concurrency,
        }

    async def _worker(self, queue_name: str) -> None:
        queue = self._queues[queue_name]
        while True:
            task_id = await queue.get()
            if task_id is None: queue.task_done(); return
            async with self._lock:
                self._pending[queue_name].discard(task_id); self._running[queue_name].add(task_id)
            try: await self.process(task_id)
            except Exception as exc: await self._fail(task_id, exc)
            finally:
                async with self._lock: self._running[queue_name].discard(task_id)
                queue.task_done()

    async def process(self, task_id: str) -> None:
        task = self.repository.get_task(task_id)
        if not task or task["status"] in TERMINAL or task["status"] == "waiting_approval": return
        if task["stage"] in {"confirmed", "generating", "assembling"}: await self._execute(task)
        else: await self._plan(task)

    def _task_assets(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        ids = list(task.get("params", {}).get("asset_ids") or [])
        return [asset for asset_id in ids if (asset := self.repository.get_asset(str(asset_id), client_id=task["client_id"]))]

    def _asset_context(self, assets: list[dict[str, Any]]) -> str:
        ids = [asset["id"] for asset in assets]
        if not ids: return ""
        with self.repository.db.transaction() as conn:
            rows = conn.execute("SELECT text_content,structured_json FROM asset_extractions WHERE asset_id IN (" + ",".join("?" for _ in ids) + ") ORDER BY created_at", ids).fetchall()
        return "\n".join(str(row["text_content"] or row["structured_json"] or "") for row in rows)[:12000]

    async def _plan(self, task: dict[str, Any]) -> None:
        params = task.get("params", {}); kind = task["kind"]; assets = self._task_assets(task)
        self.repository.update_task(task["id"], {"status": "planning", "stage": "analyzing", "progress": 0.08})
        if kind == "image":
            reference_urls = [a["storage_uri"] for a in assets if a.get("media_type") == "image" and a.get("storage_uri")]
            self.repository.reserve(
                client_id=task["client_id"], resource="image", units=1, task_id=task["id"],
                client_limit=int(params.get("client_image_limit") or 1000), global_limit=self.global_image_limit,
            )
            try:
                generated = await self.provider.generate_image(
                    prompt=f"{params.get('prompt') or '根据参考素材生成商业图片'}。9:16竖屏，真实商业摄影，无字幕无水印。",
                    reference_urls=reference_urls[:9], request_id=task["id"], metadata={"task_id": task["id"]},
                )
                if not generated.result_url:
                    raise ProductionError("图片生成未返回结果")
                asset = self.repository.create_asset(
                    client_id=task["client_id"], source_type="generated", media_type="image",
                    storage_uri=generated.result_url, status="ready", metadata={"task_id": task["id"]},
                )
                self.repository.commit(task_id=task["id"], resource="image", client_id=task["client_id"])
            except Exception:
                self.repository.release(task_id=task["id"], resource="image", client_id=task["client_id"])
                raise
            await self._complete(task, {"assets": [asset]}, media_assets=[asset])
            return
        video_assets = [a for a in assets if a.get("media_type") == "video" and a.get("storage_uri")]
        if kind == "reverse":
            if not video_assets: raise ProductionError("逆向分析需要一个视频或视频链接")
            self.repository.update_task(task["id"], {"status": "planning", "stage": "reverse_analysis", "progress": 0.2})
            async with self._planning_lock:
                result = await self.analysis.analyze(video_assets[0]["storage_uri"], request_id=task["id"], goal=str(params.get("prompt") or ""))
            await self._complete(task, result, media_assets=[])
            return
        if kind == "voice_replace":
            if not video_assets or not self.audio: raise ProductionError("声音替换需要源视频且声音服务必须可用")
            voice_text = str(params.get("voice_text") or params.get("prompt") or "").strip()
            if not voice_text: raise ProductionError("声音替换需要新的口播文本")
            result = await self.audio.replace(video_assets[0]["storage_uri"], voice_text, voice_id=params.get("voice_id"), request_id=task["id"])
            asset = self.repository.create_asset(client_id=task["client_id"], source_type="generated", media_type="video", storage_uri=result["result_url"], status="ready", metadata={"task_id": task["id"], "operation": "voice_replace", "qc": result.get("probe")})
            await self._complete(task, result, media_assets=[asset])
            return
        duration = int(params.get("duration_seconds") or 0)
        if duration < 4: raise ProductionError("请先确认视频总时长（至少4秒）")
        batch_count = max(1, min(20, int(params.get("batch_count") or 1)))
        durations = split_duration(duration)
        image_urls = [a["storage_uri"] for a in assets if a.get("media_type") == "image" and a.get("storage_uri")]
        video_urls = [a["storage_uri"] for a in video_assets]
        async with self._planning_lock:
            raw = await self.provider.understand(
                text=planning_prompt(brief=str(params.get("prompt") or ""), tool=kind, durations=durations, context=self._asset_context(assets)),
                image_urls=image_urls[:9], video_urls=video_urls[:3], request_id=f"{task['id']}:plan",
            )
        shots = normalize_plan(raw, brief=str(params.get("prompt") or ""), durations=durations, tool=kind)
        image_units = len(shots) * batch_count
        self.repository.reserve(client_id=task["client_id"], resource="image", units=image_units, task_id=task["id"], client_limit=int(params.get("client_image_limit") or 1000), global_limit=self.global_image_limit)
        storyboard_rows = []
        try:
            for shot in shots:
                result = await self.provider.generate_image(prompt=f"商业短视频分镜图，第{shot.ordinal}镜：{shot.visual}。{shot.action}。{shot.camera}。9:16，真实摄影，无字幕无水印。", reference_urls=image_urls[:2], request_id=f"{task['id']}:storyboard:{shot.ordinal}", metadata={"task_id": task["id"], "shot": shot.ordinal})
                asset = self.repository.create_asset(client_id=task["client_id"], source_type="storyboard", media_type="image", storage_uri=result.result_url, status="ready", metadata={"task_id": task["id"], "shot": shot.ordinal})
                storyboard_rows.append({**shot.as_dict(), "description": shot.visual, "duration_seconds": shot.duration, "image_asset_id": asset["id"], "image_url": result.result_url, "status": "ready"})
            self.repository.commit(task_id=task["id"], resource="image", client_id=task["client_id"])
        except Exception:
            self.repository.release(task_id=task["id"], resource="image", client_id=task["client_id"])
            raise
        board = self.repository.save_storyboard(task["id"], storyboard_rows, summary=str(raw.get("summary") if isinstance(raw, dict) else "") or "故事板已生成", status="waiting_approval", client_id=task["client_id"])
        message = self.repository.add_message(task["conversation_id"], role="assistant", kind="storyboard", content_text="故事板已完成。确认镜头、时长和额度后再开始生成视频。", content={"task_id": task["id"], "storyboard": board, "estimated_video_units": len(shots) * batch_count, "target_duration": duration}, client_id=task["client_id"])
        for index, row in enumerate(storyboard_rows): self.repository.bind_asset(message["id"], row["image_asset_id"], usage="storyboard", ordinal=index, client_id=task["client_id"])
        latest = self.repository.get_task(task["id"])
        self.repository.update_task(task["id"], {"result_message_id": message["id"], "status": "waiting_approval", "stage": "storyboard_review", "progress": 0.35, "result": {"storyboard": board, "estimated_video_units": len(shots) * batch_count}}, expected_version=latest["version"])

    async def confirm(self, task_id: str, *, client_id: str, expected_version: int, approve: bool, note: str = "") -> dict[str, Any]:
        task = self.repository.get_task(task_id, client_id=client_id)
        if not task or task["status"] != "waiting_approval": raise WorkspaceConflict("task is not waiting for storyboard approval")
        if task["version"] != expected_version: raise WorkspaceConflict("task version changed")
        if not approve:
            params = {**task["params"], "revision_note": note}
            updated = self.repository.update_task(task_id, {"params": params, "status": "queued", "stage": "revision_requested", "progress": 0.1}, client_id=client_id, expected_version=expected_version)
            await self.enqueue(task_id); return updated
        shots = self.repository.list_shots(task_id, client_id=client_id); units = len(shots) * max(1, int(task["params"].get("batch_count") or 1))
        self.repository.reserve(client_id=client_id, resource="video", units=units, task_id=task_id, client_limit=int(task["params"].get("client_video_limit") or 100), global_limit=self.global_video_limit)
        updated = self.repository.update_task(task_id, {"status": "queued", "stage": "confirmed", "progress": 0.4}, client_id=client_id, expected_version=expected_version)
        self.repository.add_message(task["conversation_id"], role="assistant", kind="status", content_text=f"故事板已确认，开始生成 {len(shots)} 个镜头，预计消耗 {units} 条视频额度。", content={"task_id": task_id, "video_units": units}, client_id=client_id)
        await self.enqueue(task_id); return updated

    async def _wait_video(self, result: Any, request_id: str) -> Any:
        deadline = asyncio.get_running_loop().time() + self.poll_timeout
        while result.status not in {"success", "failed", "cancelled"}:
            if asyncio.get_running_loop().time() >= deadline: raise ProductionError("视频生成等待超时，任务编号已保留")
            await asyncio.sleep(self.poll_interval); result = await self.provider.poll_video(result.submit_id, request_id=request_id)
        if result.status != "success" or not result.result_url: raise ProductionError(result.failure_reason or "视频生成失败")
        await self._probe_video(result.result_url, request_id=f"{request_id}:qc")
        return result

    async def _probe_video(self, url: str, *, request_id: str) -> dict[str, Any]:
        probe = await self.provider.probe_media(url, request_id=request_id)
        streams = probe.get("streams") if isinstance(probe, dict) else []
        if not isinstance(streams, list) or not any(item.get("codec_type") == "video" for item in streams):
            raise ProductionError("技术质检未检测到有效视频轨")
        duration = float(probe.get("duration") or (probe.get("format") or {}).get("duration") or 0)
        if duration <= 0:
            raise ProductionError("技术质检未检测到有效视频时长")
        return probe

    async def _execute(self, task: dict[str, Any]) -> None:
        params = task["params"]; assets = self._task_assets(task); shots = self.repository.list_shots(task["id"], client_id=task["client_id"])
        if not shots: raise ProductionError("任务缺少已确认故事板")
        self.repository.update_task(task["id"], {"status": "generating", "stage": "generating", "progress": 0.45})
        source_videos = [a["storage_uri"] for a in assets if a.get("media_type") == "video" and a.get("storage_uri")]
        replacement_images = [a["storage_uri"] for a in assets if a.get("media_type") == "image" and a.get("storage_uri")]
        batch_count = max(1, int(params.get("batch_count") or 1)); final_assets = []
        if task["kind"] == "replace":
            if not source_videos or not replacement_images: raise ProductionError("定向替换需要源视频和替换参考图")
            start = float(params.get("replace_start") or 0); end = float(params.get("replace_end") or shots[0].get("duration_seconds") or 5)
            async with self._generation_slots:
                generated = await self.provider.submit_video(prompt=f"参考视频1保持镜头、动作、光线和节奏不变，只替换{params.get('replace_target') or '指定元素'}。替换内容严格参考图片1。保持其他人物、商品、场景、声音和构图不变。{params.get('prompt') or ''}", image_urls=replacement_images[:1], video_urls=source_videos[:1], duration=max(4, min(15, round(end - start))), request_id=f"{task['id']}:replace", metadata={"task_id": task["id"], "operation": "targeted_replace"})
                generated = await self._wait_video(generated, f"{task['id']}:replace")
            output = await replace_segment_file(source_videos[0], generated.result_url, start=start, end=end)
            final_url = await self.provider.upload_blob(f"replacement-{task['id']}.mp4", output, "video/mp4", stage="video.replace", request_id=task["id"])
            probe = await self._probe_video(final_url, request_id=f"{task['id']}:replace:qc")
            final_assets.append(self.repository.create_asset(client_id=task["client_id"], source_type="generated", media_type="video", storage_uri=final_url, status="ready", metadata={"task_id": task["id"], "operation": "targeted_replace", "range": [start, end], "qc": probe}))
        else:
            progress_lock = asyncio.Lock()
            completed_segments = 0

            async def generate_variant(variant: int) -> dict[str, Any]:
                nonlocal completed_segments
                segment_urls: list[str] = []
                for index, shot in enumerate(shots):
                    image_asset = self.repository.get_asset(str(shot.get("image_asset_id")), client_id=task["client_id"])
                    video_refs = []
                    if task["kind"] == "replicate" and source_videos: video_refs.append(source_videos[0])
                    if segment_urls: video_refs.append(segment_urls[-1])
                    prompt = str(shot.get("payload", {}).get("prompt") or shot.get("description") or params.get("prompt") or "")
                    reference_rules = ["图片1是当前镜头的首帧、主体身份和产品外观基准"]
                    if task["kind"] == "replicate" and source_videos:
                        reference_rules.append("视频1仅参考镜头结构、动作因果和节奏，不复制原人物、品牌、字幕或音乐")
                    if segment_urls:
                        previous_slot = 2 if task["kind"] == "replicate" and source_videos else 1
                        reference_rules.append(f"视频{previous_slot}是上一镜头，只用于动作、构图和时间连续性")
                    async with self._generation_slots:
                        result = await self.provider.submit_video(prompt=f"{'；'.join(reference_rules)}。{prompt}。第{variant + 1}个差异化版本。保持故事板主体与9:16构图，无字幕无水印。", image_urls=[image_asset["storage_uri"]] if image_asset and image_asset.get("storage_uri") else replacement_images[:1], video_urls=video_refs[:3], duration=int(round(float(shot.get("duration_seconds") or 5))), request_id=f"{task['id']}:v{variant + 1}:s{index + 1}", metadata={"task_id": task["id"], "variant": variant + 1, "shot": index + 1, "reference_manifest": {"image1": "storyboard_identity", "video1": "source_structure" if task["kind"] == "replicate" and source_videos else "previous_continuity"}})
                        result = await self._wait_video(result, f"{task['id']}:v{variant + 1}:s{index + 1}")
                    segment_urls.append(result.result_url)
                    async with progress_lock:
                        completed_segments += 1
                        progress = 0.45 + 0.45 * (completed_segments / (batch_count * len(shots)))
                        self.repository.update_task(task["id"], {"status": "generating", "stage": f"镜头 {completed_segments}/{batch_count * len(shots)}", "progress": progress, "result": {"segments": segment_urls, "variant": variant + 1}})
                async with self._generation_slots:
                    transcode = await self.provider.transcode(segment_urls, filename=f"{task['id']}-variant-{variant + 1}.mp4", request_id=f"{task['id']}:assemble:{variant + 1}")
                if not transcode.result_url:
                    raise ProductionError("视频拼接未返回结果")
                probe = await self._probe_video(transcode.result_url, request_id=f"{task['id']}:assemble:{variant + 1}:qc")
                return self.repository.create_asset(client_id=task["client_id"], source_type="generated", media_type="video", storage_uri=transcode.result_url, status="ready", metadata={"task_id": task["id"], "variant": variant + 1, "segments": segment_urls, "qc": probe})

            final_assets = list(await asyncio.gather(*(generate_variant(variant) for variant in range(batch_count))))
            self.repository.update_task(task["id"], {"status": "assembling", "stage": "assembling", "progress": 0.95})
        self.repository.commit(task_id=task["id"], resource="video", client_id=task["client_id"])
        await self._complete(task, {"assets": final_assets, "target_duration": params.get("duration_seconds")}, media_assets=final_assets)

    async def _complete(self, task: dict[str, Any], result: dict[str, Any], *, media_assets: list[dict[str, Any]]) -> None:
        kind = "media" if media_assets else "analysis"
        text = "生产完成，结果已返回对话。" if media_assets else "分析完成，已生成可复用的结构化结果。"
        message = self.repository.add_message(task["conversation_id"], role="assistant", kind=kind, content_text=text, content={"task_id": task["id"], "result": result}, client_id=task["client_id"])
        for index, asset in enumerate(media_assets): self.repository.bind_asset(message["id"], asset["id"], usage="result", ordinal=index, client_id=task["client_id"])
        now = datetime.now(timezone.utc).isoformat()
        self.repository.update_task(task["id"], {"result_message_id": message["id"], "status": "succeeded", "stage": "completed", "progress": 1, "result": result, "finished_at": now})
        with self.repository.db.transaction(immediate=True) as conn:
            conn.execute("""INSERT OR REPLACE INTO training_examples(id,client_id,conversation_id,input_message_id,output_message_id,task_id,schema_version,input_json,output_json,labels_json,quality_json,eligibility,created_at,updated_at) VALUES(?,?,?,?,?,?,2,?,?,?,?,'eligible',?,?)""", (uuid4().hex, task["client_id"], task["conversation_id"], task.get("request_message_id"), message["id"], task["id"], json.dumps(task.get("params", {}), ensure_ascii=False), json.dumps(result, ensure_ascii=False), json.dumps({"kind": task["kind"]}, ensure_ascii=False), json.dumps({"status": "succeeded"}, ensure_ascii=False), now, now))
            conn.execute(
                """INSERT INTO activity_events(ts,client_id,event_type,conversation_id,message_id,task_id,
                dedupe_key,payload_json) VALUES(?,?,?,?,?,?,?,?)""",
                (now, task["client_id"], "task.succeeded", task["conversation_id"], message["id"], task["id"],
                 f"task.succeeded:{task['id']}", json.dumps(result, ensure_ascii=False)),
            )
        if self.events:
            params = task.get("params", {})
            mode = Mode.IMAGE if task["kind"] == "image" else Mode.VIDEO
            urls = [asset.get("storage_uri") for asset in media_assets] or [None]
            video_units = len(self.repository.list_shots(task["id"], client_id=task["client_id"])) * max(1, int(params.get("batch_count") or 1)) if mode is Mode.VIDEO else 0
            for index, url in enumerate(urls):
                self.events.write(EventRecord(
                    ts=datetime.now(timezone.utc), access_code=task["client_id"], mode=mode,
                    preset_id=task["kind"], template_version="chat-os-v2", prompt_user=str(params.get("prompt") or ""),
                    prompt_final=str(params.get("prompt") or ""), params=params,
                    model="gpt-image-2" if mode is Mode.IMAGE else "seedance2.0fast_vip",
                    result_url=url, latency_ms=None, cost_units=(1 if mode is Mode.IMAGE else video_units if index == 0 else 0),
                    action=EventAction.GENERATE, job_id=task["id"], client_id=task["client_id"],
                    queue_name=mode.value, provider_attempt=1, skill_trace={"workflow": "storyboard-confirm-generate", "version": 2},
                ))

    async def _fail(self, task_id: str, exc: Exception) -> None:
        task = self.repository.get_task(task_id)
        if not task: return
        for resource in ("image", "video"):
            try: self.repository.release(task_id=task_id, resource=resource, client_id=task["client_id"])
            except Exception: pass
        code = getattr(exc, "code", "PRODUCTION_FAILED"); now = datetime.now(timezone.utc).isoformat()
        self.repository.update_task(task_id, {"status": "failed", "stage": "failed", "error_code": code, "error_message": str(exc), "finished_at": now})
        self.repository.add_message(task["conversation_id"], role="assistant", kind="error", content_text=f"任务失败：{exc}", content={"task_id": task_id, "error_code": code}, client_id=task["client_id"])
        with self.repository.db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO activity_events(ts,client_id,event_type,conversation_id,task_id,
                dedupe_key,payload_json) VALUES(?,?,?,?,?,?,?)""",
                (now, task["client_id"], "task.failed", task["conversation_id"], task_id,
                 f"task.failed:{task_id}", json.dumps({"error_code": code, "message": str(exc)}, ensure_ascii=False)),
            )
