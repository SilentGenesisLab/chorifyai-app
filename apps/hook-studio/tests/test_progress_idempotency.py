from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from app.main import app


def _configure(monkeypatch, tmp_path):
    codes = tmp_path / "access_codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [{
        "id": "client-a", "code": "code-a", "client_name": "A", "role": "client",
        "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True,
    }]}), encoding="utf-8")
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/")
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", str(codes))
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("HOOK_STUDIO_PROVIDER_MODE", "fake")


def test_message_submission_idempotency_survives_replay(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "code-a"})
        conversation = client.post("/api/studio/conversations", json={"title": "dedupe"}).json()
        headers = {"Idempotency-Key": "browser-submit-0001"}
        payload = {"text": "生成一张产品首帧", "tool": "create_image", "links": "[]"}

        first = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages", data=payload, headers=headers,
        )
        replay = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages", data=payload, headers=headers,
        )

        assert first.status_code == replay.status_code == 202
        assert replay.json()["replayed"] is True
        assert first.json()["task"]["id"] == replay.json()["task"]["id"]
        tasks = client.get(f"/api/studio/tasks?conversation_id={conversation['id']}").json()["items"]
        messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        assert len(tasks) == 1
        assert len([item for item in messages if item["role"] == "user"]) == 1


def test_snapshot_splits_image_and_video_terminal_counts(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "code-a"})
        conversation = client.post("/api/studio/conversations", json={"title": "counts"}).json()
        repo = client.app.state.workspace
        image = repo.create_task(
            client_id="client-a", conversation_id=conversation["id"], kind="image", title="image",
        )
        video = repo.create_task(
            client_id="client-a", conversation_id=conversation["id"], kind="create", title="video",
        )
        repo.update_task(image["id"], {"status": "succeeded"}, client_id="client-a")
        repo.update_task(video["id"], {"status": "failed"}, client_id="client-a")

        counts = client.get("/api/studio/bootstrap").json()["queues"]
        assert counts["image_succeeded"] == 1
        assert counts["image_failed"] == 0
        assert counts["video_succeeded"] == 0
        assert counts["video_failed"] == 1
        assert counts["succeeded"] == counts["failed"] == 1
