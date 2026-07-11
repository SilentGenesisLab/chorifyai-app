from __future__ import annotations

import asyncio

from app.db import Database
from app.repositories.workspace import WorkspaceRepository
from app.services.workflow_events import WorkflowEventStream


def test_sse_replays_after_last_event_and_emits_stable_envelope(tmp_path):
    db = Database(tmp_path / "events.sqlite3"); db.initialize(); repo = WorkspaceRepository(db)
    conversation = repo.create_conversation(client_id="a", title="events")
    task = repo.create_task(client_id="a", conversation_id=conversation["id"], kind="create", title="video")
    first = repo.append_workflow_event(task["id"], client_id="a", event_type="task.started", payload={"n": 1})
    second = repo.append_workflow_event(task["id"], client_id="a", event_type="shot.ready", payload={
        "n": 2, "label": "镜头就绪", "message": "第1镜已完成", "state": "succeeded",
        "input_count": 1, "output_count": 3, "counts": {"image_queued": 0, "video_running": 1},
    })

    async def read_one():
        stream = WorkflowEventStream(repo, poll_seconds=0.01, heartbeat_seconds=0.02)
        generator = stream.iter_sse(task["id"], client_id="a", last_event_id=first["id"])
        value = await anext(generator)
        await generator.aclose()
        return value

    event = asyncio.run(read_one())
    assert f"id: {second['id']}" in event
    assert "event: hook.event.v1" in event
    assert '"type":"shot.ready"' in event
    assert '"schema":"hook.event.v1"' in event
    assert '"public_label":"镜头就绪"' in event
    assert '"message":"第1镜已完成"' in event
    assert '"queue":{"image_queued":0,"video_running":1}' in event
