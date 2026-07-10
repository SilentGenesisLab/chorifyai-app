from __future__ import annotations

import time

import yaml
from fastapi.testclient import TestClient

from app.main import app


def _configure(monkeypatch, tmp_path):
    codes = tmp_path / "access_codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [{
        "id": "client-01", "code": "client-code", "client_name": "测试客户",
        "role": "client", "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True,
    }]}), encoding="utf-8")
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/")
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", str(codes))
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("HOOK_STUDIO_PROVIDER_MODE", "fake")


def _wait_task(client: TestClient, task_id: str, expected: set[str]) -> dict:
    for _ in range(100):
        task = client.get(f"/api/studio/tasks/{task_id}").json()
        if task["status"] in expected:
            return task
        time.sleep(0.01)
    raise AssertionError(f"task {task_id} did not reach {expected}")


def test_multiconversation_image_and_training_capture(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "client-code"})
        conversation = client.post("/api/studio/conversations", json={"title": "商品主图"}).json()
        submitted = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages",
            data={"text": "生成一张美区家居场景中的桌面灯产品图", "tool": "create_image", "links": "[]"},
        )
        assert submitted.status_code == 202
        task = _wait_task(client, submitted.json()["task"]["id"], {"succeeded", "failed"})
        assert task["status"] == "succeeded"
        messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        assert messages[-1]["kind"] == "media"
        assert messages[-1]["assets"][0]["type"] == "image"
        usage = client.get("/api/studio/bootstrap").json()["usage"]
        assert usage["image_used"] == 1
        with app.state.db.transaction() as conn:
            assert conn.execute("SELECT COUNT(*) n FROM training_examples").fetchone()["n"] == 1


def test_long_video_storyboard_confirmation_flow(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "client-code"})
        conversation = client.post("/api/studio/conversations", json={"title": "长视频"}).json()
        submitted = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages",
            data={"text": "制作完整的60秒商品演示视频", "tool": "create_video", "duration_seconds": "60", "links": "[]"},
        ).json()
        waiting = _wait_task(client, submitted["task"]["id"], {"waiting_confirmation", "failed"})
        assert waiting["status"] == "waiting_confirmation"
        messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        board = next(item["storyboard"] for item in messages if item["kind"] == "storyboard")
        assert board["total_duration_seconds"] == 60
        assert len(board["shots"]) >= 4
        approved = client.post(f"/api/studio/storyboards/{board['id']}/confirm", json={"approved": True, "feedback": ""})
        assert approved.status_code == 200
        done = _wait_task(client, submitted["task"]["id"], {"succeeded", "failed"})
        assert done["status"] == "succeeded"
        refreshed = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        confirmed = next(item["storyboard"] for item in refreshed if item["kind"] == "storyboard")
        assert confirmed["status"] == "confirmed"
        assert any(item["assets"] and item["assets"][0]["type"] == "video" for item in refreshed)
