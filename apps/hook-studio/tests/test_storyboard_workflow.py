from __future__ import annotations

import time

import yaml
from fastapi.testclient import TestClient

from app.main import app


def _configure(monkeypatch, tmp_path):
    codes = tmp_path / "access_codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [
        {"id": "client-a", "code": "code-a", "client_name": "A", "role": "client", "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True},
        {"id": "client-b", "code": "code-b", "client_name": "B", "role": "client", "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True},
    ]}), encoding="utf-8")
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/")
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", str(codes))
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("HOOK_STUDIO_PROVIDER_MODE", "fake")


def _wait(client, task_id):
    for _ in range(200):
        task = client.get(f"/api/studio/tasks/{task_id}").json()
        if task["status"] in {"waiting_confirmation", "failed"}: return task
        time.sleep(0.01)
    raise AssertionError("task did not produce storyboard")


def test_storyboard_detail_has_panels_and_stale_patch_is_rejected(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "code-a"})
        conversation = client.post("/api/studio/conversations", json={"title": "full"}).json()
        submitted = client.post(f"/api/studio/conversations/{conversation['id']}/messages", data={"text": "制作8秒产品视频", "tool": "create_video", "duration_seconds": "8", "links": "[]"}).json()
        _wait(client, submitted["task"]["id"])
        messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        board_id = next(item["storyboard"]["id"] for item in messages if item["kind"] == "storyboard")
        board = client.get(f"/api/studio/storyboards/{board_id}").json()
        assert all(len(shot["panels"]) >= 1 for shot in board["shots"])
        assert board["task_id"] == submitted["task"]["id"]
        assert board["guard"]["can_produce"] is False
        assert board["guard"]["blockers"]
        assert board["coverage"]["panel_required"] >= board["coverage"]["shot_total"]
        assert all(panel["status"] == "draft" and panel["approval"] is None for shot in board["shots"] for panel in shot["panels"])
        shot = board["shots"][0]
        patched = client.patch(f"/api/studio/storyboards/{board_id}/shots/{shot['id']}", json={"expected_version": board["revision"], "description": "新的清晰描述"})
        assert patched.status_code == 200
        stale = client.patch(f"/api/studio/storyboards/{board_id}/shots/{shot['id']}", json={"expected_version": board["revision"], "description": "旧请求"})
        assert stale.status_code == 409


def _create_board(client: TestClient):
    conversation = client.post("/api/studio/conversations", json={"title": "workflow"}).json()
    submitted = client.post(
        f"/api/studio/conversations/{conversation['id']}/messages",
        data={"text": "制作8秒产品视频", "tool": "create_video", "duration_seconds": "8", "links": "[]"},
    ).json()
    _wait(client, submitted["task"]["id"])
    messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
    board_id = next(item["storyboard"]["id"] for item in messages if item["kind"] == "storyboard")
    return submitted["task"]["id"], client.get(f"/api/studio/storyboards/{board_id}").json()


def test_production_is_locked_until_scoped_approvals_and_animatic(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "code-a"})
        _, board = _create_board(client)
        legacy_locked = client.post(f"/api/studio/storyboards/{board['id']}/confirm", json={"approved": True, "feedback": ""})
        assert legacy_locked.status_code == 422
        locked = client.post(f"/api/studio/storyboards/{board['id']}/produce", json={"expected_version": board["revision"]})
        assert locked.status_code == 422
        assert client.get("/api/studio/bootstrap").json()["usage"]["client_video_used"] == 0
        for shot in board["shots"]:
            for panel in shot["panels"]:
                assert client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
                    "expected_version": board["revision"], "scope": "panel", "target_id": panel["id"],
                    "decision": "approved", "feedback": "通过",
                }).status_code == 200
            assert client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
                "expected_version": board["revision"], "scope": "shot", "target_id": shot["id"],
                "decision": "approved", "feedback": "通过",
            }).status_code == 200
        client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
            "expected_version": board["revision"], "scope": "board", "target_id": board["id"],
            "decision": "approved",
        })
        animatic = client.post(f"/api/studio/storyboards/{board['id']}/animatic", json={
            "expected_version": board["revision"], "confirm": True,
        })
        assert animatic.status_code == 200
        assert animatic.json()["animatic"]["status"] == "confirmed"
        ready = client.post(f"/api/studio/storyboards/{board['id']}/produce", json={"expected_version": board["revision"]})
        assert ready.status_code == 202
        assert ready.json()["task"]["status"] in {"queued", "running"}


def test_panel_regenerate_changes_only_selected_panel_and_charges_one_image(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "code-a"})
        _, board = _create_board(client)
        before = [panel["id"] for shot in board["shots"] for panel in shot["panels"]]
        target = before[1]
        used = client.get("/api/studio/bootstrap").json()["usage"]["image_used"]
        response = client.post(f"/api/studio/storyboards/{board['id']}/panels/{target}/regenerate", json={
            "expected_version": board["revision"], "feedback": "手与产品接触点更清楚",
        })
        assert response.status_code == 200
        revised = response.json()
        after = [panel["id"] for shot in revised["shots"] for panel in shot["panels"]]
        assert target not in after
        assert len(set(before) & set(after)) == len(before) - 1
        assert revised["revision"] == board["revision"] + 1
        assert client.get("/api/studio/bootstrap").json()["usage"]["image_used"] == used + 1


def test_sse_is_tenant_scoped(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/studio/tasks/missing/events").status_code == 401
        client.post("/api/auth/login", json={"access_code": "code-a"})
        task_id, _ = _create_board(client)
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"access_code": "code-b"})
        assert client.get(f"/api/studio/tasks/{task_id}/events").status_code == 404


def test_video_duration_is_server_limited_to_four_through_sixty_seconds(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "code-a"})
        conversation = client.post("/api/studio/conversations", json={"title": "duration"}).json()
        for duration in (3, 61, 180):
            response = client.post(f"/api/studio/conversations/{conversation['id']}/messages", data={
                "text": "制作产品视频", "tool": "create_video", "duration_seconds": str(duration), "links": "[]",
            })
            assert response.status_code == 422
        accepted = client.post(f"/api/studio/conversations/{conversation['id']}/messages", data={
            "text": "制作产品视频", "tool": "create_video", "duration_seconds": "60", "links": "[]",
        })
        assert accepted.status_code == 202
