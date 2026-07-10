import json

import pytest

from app.db import Database
from app.repositories.workspace import (
    QuotaExceeded,
    WorkspaceConflict,
    WorkspaceRepository,
)


def _repo(tmp_path):
    db = Database(tmp_path / "workspace.sqlite3")
    db.initialize()
    return db, WorkspaceRepository(db)


def test_conversations_messages_assets_and_soft_delete(tmp_path):
    _, repo = _repo(tmp_path)
    conversation = repo.create_conversation(client_id="c1", title="新品视频")
    message = repo.add_message(
        conversation["id"], client_id="c1", role="user", content_text="解析这些素材",
    )
    asset = repo.create_asset(
        client_id="c1", source_type="upload", media_type="video",
        filename="demo.mp4", mime_type="video/mp4", storage_uri="oss://demo.mp4",
        metadata={"duration": 12},
    )
    binding = repo.bind_asset(message["id"], asset["id"], client_id="c1")

    assert message["seq"] == 1
    assert repo.get_asset(asset["id"], client_id="c1")["metadata"]["duration"] == 12
    assert binding["ordinal"] == 0
    assert [item["content_text"] for item in repo.list_messages(conversation["id"], client_id="c1")] == ["解析这些素材"]
    assert repo.get_conversation(conversation["id"], client_id="other") is None
    assert repo.delete_conversation(conversation["id"], client_id="c1") is True
    assert repo.list_conversations("c1") == []
    assert len(repo.list_conversations("c1", include_deleted=True)) == 1


def test_tasks_storyboard_and_optimistic_version(tmp_path):
    _, repo = _repo(tmp_path)
    conversation = repo.create_conversation(client_id="c1")
    request = repo.add_message(conversation["id"], client_id="c1", role="user", content_text="做60秒视频")
    task = repo.create_task(
        client_id="c1", conversation_id=conversation["id"], request_message_id=request["id"],
        kind="long_video", title="60秒品牌片", params={"duration_seconds": 60},
    )
    image = repo.create_asset(
        client_id="c1", source_type="generated", media_type="image", storage_uri="oss://shot-1.jpg",
    )
    storyboard = repo.save_storyboard(task["id"], [
        {"title": "开场", "duration_seconds": 5, "image_asset_id": image["id"], "camera": "推近"},
        {"title": "证明", "duration_seconds": 8},
    ], client_id="c1")
    updated = repo.update_task(
        task["id"], {"status": "awaiting_confirmation", "stage": "storyboard", "progress": 0.25},
        client_id="c1", expected_version=1,
    )

    assert storyboard["version"] == 1
    assert [shot["title"] for shot in repo.list_shots(task["id"], client_id="c1")] == ["开场", "证明"]
    assert updated["version"] == 2
    assert repo.list_tasks("c1", conversation_id=conversation["id"])[0]["params"]["duration_seconds"] == 60
    with pytest.raises(WorkspaceConflict, match="version"):
        repo.update_task(task["id"], {"progress": 0.5}, expected_version=1)


def test_quota_reservation_commit_release_and_limits(tmp_path):
    _, repo = _repo(tmp_path)
    conversation = repo.create_conversation(client_id="c1")
    first = repo.create_task(client_id="c1", conversation_id=conversation["id"], kind="video", title="A")
    second = repo.create_task(client_id="c1", conversation_id=conversation["id"], kind="video", title="B")

    reserved = repo.reserve(
        client_id="c1", resource="video_seconds", units=60, client_limit=90,
        global_limit=1000, task_id=first["id"], day_cn="2026-07-10",
    )
    repeated = repo.reserve(
        client_id="c1", resource="video_seconds", units=60, client_limit=90,
        global_limit=1000, task_id=first["id"], day_cn="2026-07-10",
    )
    assert repeated["reservation"]["id"] == reserved["reservation"]["id"]
    assert repo.commit(task_id=first["id"], resource="video_seconds")["state"] == "committed"
    with pytest.raises(QuotaExceeded):
        repo.reserve(
            client_id="c1", resource="video_seconds", units=31, client_limit=90,
            global_limit=1000, task_id=second["id"], day_cn="2026-07-10",
        )
    released = repo.reserve(
        client_id="c1", resource="image", units=100, client_limit=1000,
        global_limit=10000, task_id=second["id"], day_cn="2026-07-10",
    )
    assert repo.release(released["reservation"]["id"])["state"] == "released"
    assert repo.quota_snapshot(
        client_id="c1", resource="image", client_limit=1000,
        global_limit=10000, day_cn="2026-07-10",
    )["client_used"] == 0


def test_legacy_job_backfill_is_idempotent(tmp_path):
    db, repo = _repo(tmp_path)
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """INSERT INTO jobs(
            id,client_id,mode,preset_id,template_version,prompt_user,prompt_final,
            params_json,model,status,queue_name,result_url,result_meta_json,queued_at,finished_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("legacy-video", "c1", "video", "pain-point", "1", "旧用户提示", "旧完整提示",
             json.dumps({"duration": 5, "reservation_day": "2026-07-10"}), "legacy-model",
             "succeeded", "video", "https://cdn.example/video.mp4", json.dumps({"qc": {"passed": True}}),
             "2026-07-10T01:00:00+00:00", "2026-07-10T01:02:00+00:00"),
        )

    first = repo.backfill_legacy()
    second = repo.backfill_legacy()

    assert first == {"conversations": 1, "tasks": 1, "messages": 2, "assets": 1, "training_examples": 1}
    assert second == {"conversations": 0, "tasks": 0, "messages": 0, "assets": 0, "training_examples": 0}
    conversations = repo.list_conversations("c1")
    tasks = repo.list_tasks("c1")
    messages = repo.list_messages(conversations[0]["id"], client_id="c1")
    with db.transaction() as conn:
        counts = {
            name: conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
            for name in ("jobs", "task_jobs", "message_assets", "training_examples", "quota_ledger")
        }
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert tasks[0]["result"]["result_url"].endswith("video.mp4")
    assert counts == {"jobs": 1, "task_jobs": 1, "message_assets": 1, "training_examples": 1, "quota_ledger": 1}
