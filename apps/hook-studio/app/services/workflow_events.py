from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator, Any

from app.repositories.workspace import WorkspaceRepository


class WorkflowEventStream:
    """Durable SQLite replay with lightweight polling and SSE heartbeats."""

    def __init__(
        self, repository: WorkspaceRepository, *, poll_seconds: float = 0.5,
        heartbeat_seconds: float = 15.0,
    ) -> None:
        self.repository = repository
        self.poll_seconds = max(0.01, poll_seconds)
        self.heartbeat_seconds = max(self.poll_seconds, heartbeat_seconds)

    @staticmethod
    def encode(event: dict[str, Any]) -> str:
        envelope = event.get("envelope") or {
            "schema": "hook.event.v1", "id": event["id"], "task_id": event["task_id"],
            "type": event["event_type"], "ts": event["created_at"], "data": {},
        }
        payload = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
        return f"id: {event['id']}\nevent: hook.event.v1\ndata: {payload}\n\n"

    async def iter_sse(
        self, task_id: str, *, client_id: str, last_event_id: int = 0,
    ) -> AsyncIterator[str]:
        cursor = max(0, int(last_event_id))
        elapsed = 0.0
        while True:
            events = self.repository.list_workflow_events(
                task_id, client_id=client_id, after_id=cursor, limit=200,
            )
            if events:
                for event in events:
                    cursor = int(event["id"])
                    yield self.encode(event)
                elapsed = 0.0
                continue
            await asyncio.sleep(self.poll_seconds)
            elapsed += self.poll_seconds
            if elapsed >= self.heartbeat_seconds:
                heartbeat = {
                    "schema": "hook.event.v1", "task_id": task_id, "type": "heartbeat",
                    "ts": datetime.now(timezone.utc).isoformat(), "data": {"last_event_id": cursor},
                }
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat, ensure_ascii=False, separators=(',', ':'))}\n\n"
                elapsed = 0.0
