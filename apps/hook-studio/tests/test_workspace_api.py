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


def _approve_full_storyboard(client: TestClient, board_id: str) -> dict:
    board = client.get(f"/api/studio/storyboards/{board_id}").json()
    for shot in board["shots"]:
        for panel in shot["panels"]:
            response = client.post(f"/api/studio/storyboards/{board_id}/decisions", json={
                "expected_version": board["revision"], "scope": "panel", "scope_id": panel["id"],
                "decision": "approved",
            })
            assert response.status_code == 200
        response = client.post(f"/api/studio/storyboards/{board_id}/decisions", json={
            "expected_version": board["revision"], "scope": "shot", "scope_id": shot["id"],
            "decision": "approved",
        })
        assert response.status_code == 200
    response = client.post(f"/api/studio/storyboards/{board_id}/decisions", json={
        "expected_version": board["revision"], "scope": "storyboard", "scope_id": board_id,
        "decision": "approved",
    })
    assert response.status_code == 200
    response = client.post(f"/api/studio/storyboards/{board_id}/animatic", json={
        "expected_version": board["revision"], "confirm": True,
    })
    assert response.status_code == 200
    return response.json()


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
        _approve_full_storyboard(client, board["id"])
        approved = client.post(f"/api/studio/storyboards/{board['id']}/confirm", json={"approved": True, "feedback": ""})
        assert approved.status_code == 200
        done = _wait_task(client, submitted["task"]["id"], {"succeeded", "failed"})
        assert done["status"] == "succeeded"
        refreshed = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        confirmed = next(item["storyboard"] for item in refreshed if item["kind"] == "storyboard")
        assert confirmed["status"] == "confirmed"
        assert any(item["assets"] and item["assets"][0]["type"] == "video" for item in refreshed)


def test_batch_variants_complete_as_one_task(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "client-code"})
        conversation = client.post("/api/studio/conversations", json={"title": "批量"}).json()
        submitted = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages",
            data={"text": "批量生成3条差异化产品视频", "tool": "batch_production", "duration_seconds": "4", "links": "[]"},
        ).json()
        _wait_task(client, submitted["task"]["id"], {"waiting_confirmation"})
        board = next(
            item["storyboard"] for item in client.get(
                f"/api/studio/conversations/{conversation['id']}/messages"
            ).json()["items"] if item["kind"] == "storyboard"
        )
        _approve_full_storyboard(client, board["id"])
        client.post(f"/api/studio/storyboards/{board['id']}/confirm", json={"approved": True, "feedback": ""})
        done = _wait_task(client, submitted["task"]["id"], {"succeeded", "failed"})
        assert done["status"] == "succeeded"
        messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        assert len(messages[-1]["assets"]) == 3
