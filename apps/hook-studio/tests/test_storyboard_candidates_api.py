from __future__ import annotations

import time

import yaml
from fastapi.testclient import TestClient

from app.main import app


def _configure(monkeypatch, tmp_path):
    codes = tmp_path / "access_codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [
        {
            "id": "client-a", "code": "code-a", "client_name": "A", "role": "client",
            "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True,
        },
        {
            "id": "client-b", "code": "code-b", "client_name": "B", "role": "client",
            "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True,
        },
    ]}), encoding="utf-8")
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/")
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", str(codes))
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("HOOK_STUDIO_PROVIDER_MODE", "fake")
    monkeypatch.setattr("app.services.production.split_duration", lambda _duration: [4] * 8)


def _wait_for_storyboard(client: TestClient, task_id: str) -> None:
    for _ in range(300):
        task = client.get(f"/api/studio/tasks/{task_id}").json()
        if task["status"] == "waiting_confirmation":
            return
        if task["status"] == "failed":
            raise AssertionError(task)
        time.sleep(0.01)
    raise AssertionError("task did not produce storyboard")


def _create_eight_shot_board(client: TestClient) -> dict:
    conversation = client.post("/api/studio/conversations", json={"title": "N4 focused"}).json()
    response = client.post(
        f"/api/studio/conversations/{conversation['id']}/messages",
        data={
            "text": "制作32秒、八镜头产品视频",
            "tool": "create_video",
            "duration_seconds": "32",
            "links": "[]",
        },
    )
    assert response.status_code == 202
    task_id = response.json()["task"]["id"]
    _wait_for_storyboard(client, task_id)
    messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
    board_id = next(item["storyboard"]["id"] for item in messages if item["kind"] == "storyboard")
    return client.get(f"/api/studio/storyboards/{board_id}").json()


def _shot_state(shot: dict) -> dict:
    return {
        "revision": shot["revision"],
        "panel_ids": tuple(panel["id"] for panel in shot["panels"]),
        "assets": tuple(panel["selected_asset_id"] for panel in shot["panels"]),
    }


def test_eight_shot_s04_regenerate_and_candidate_switch_close_n4(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"access_code": "code-a"}).status_code == 200
        board = _create_eight_shot_board(client)

        assert len(board["shots"]) == 8
        assert board["coverage"]["shot_total"] == 8
        panel_count = sum(len(shot["panels"]) for shot in board["shots"])
        assert panel_count >= 8
        assert board["coverage"]["panel_required"] == panel_count
        assert board["coverage"]["clean_ready"] == 8

        initial = {shot["id"]: _shot_state(shot) for shot in board["shots"]}
        s04 = next(shot for shot in board["shots"] if shot["order"] == 4)
        assert 1 <= len(s04["panels"]) <= 3
        image_used = client.get("/api/studio/bootstrap").json()["usage"]["image_used"]

        regenerated_response = client.post(
            f"/api/studio/storyboards/{board['id']}/shots/{s04['id']}/regenerate",
            json={"expected_version": board["revision"], "feedback": "重做整镜动作因果"},
        )
        assert regenerated_response.status_code == 200
        regenerated = regenerated_response.json()
        assert regenerated["revision"] == board["revision"] + 1
        assert client.get("/api/studio/bootstrap").json()["usage"]["image_used"] == image_used + len(s04["panels"])

        regenerated_s04 = next(shot for shot in regenerated["shots"] if shot["id"] == s04["id"])
        assert regenerated_s04["revision"] == s04["revision"] + 1
        assert {panel["logical_key"] for panel in regenerated_s04["panels"]} == {
            panel["logical_key"] for panel in s04["panels"]
        }
        old_by_key = {panel["logical_key"]: panel for panel in s04["panels"]}
        for panel in regenerated_s04["panels"]:
            old = old_by_key[panel["logical_key"]]
            assert panel["id"] != old["id"]
            assert panel["revision"] == old["revision"] + 1
            assert panel["selected_asset_id"] != old["selected_asset_id"]
        for shot in regenerated["shots"]:
            if shot["id"] != s04["id"]:
                assert _shot_state(shot) == initial[shot["id"]]

        used_after_regenerate = client.get("/api/studio/bootstrap").json()["usage"]["image_used"]
        stale_regenerate = client.post(
            f"/api/studio/storyboards/{board['id']}/shots/{s04['id']}/regenerate",
            json={"expected_version": board["revision"], "feedback": "旧请求"},
        )
        assert stale_regenerate.status_code == 409
        assert client.get("/api/studio/bootstrap").json()["usage"]["image_used"] == used_after_regenerate

        current = regenerated_s04["panels"][0]
        history_response = client.get(
            f"/api/studio/storyboards/{board['id']}/panels/{current['id']}/candidates"
        )
        assert history_response.status_code == 200
        history = history_response.json()
        assert history["current_panel_id"] == current["id"]
        assert history["logical_key"] == current["logical_key"]
        assert [candidate["revision"] for candidate in history["candidates"]] == [2, 1]
        historical = next(candidate for candidate in history["candidates"] if not candidate["is_current"])

        approval = client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
            "expected_version": regenerated["revision"],
            "scope": "panel",
            "target_id": current["id"],
            "decision": "approved",
            "feedback": "当前候选通过",
        })
        assert approval.status_code == 200
        assert next(
            panel for shot in approval.json()["shots"] for panel in shot["panels"]
            if panel["id"] == current["id"]
        )["approved"] is True

        switched_response = client.post(
            f"/api/studio/storyboards/{board['id']}/panels/{current['id']}/candidates/{historical['id']}/select",
            json={"expected_version": regenerated["revision"]},
        )
        assert switched_response.status_code == 200
        switched = switched_response.json()
        assert switched["revision"] == regenerated["revision"] + 1
        switched_s04 = next(shot for shot in switched["shots"] if shot["id"] == s04["id"])
        assert switched_s04["revision"] == regenerated_s04["revision"] + 1
        selected = next(
            panel for panel in switched_s04["panels"] if panel["logical_key"] == current["logical_key"]
        )
        assert selected["id"] not in {current["id"], historical["id"]}
        assert selected["revision"] == current["revision"] + 1
        assert selected["selected_asset_id"] == historical["selected_asset_id"]
        assert selected["approved"] is False
        assert selected["approval"] is None

        old_approval = client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
            "expected_version": regenerated["revision"],
            "scope": "panel",
            "target_id": current["id"],
            "decision": "approved",
        })
        assert old_approval.status_code == 409
        stale_switch = client.post(
            f"/api/studio/storyboards/{board['id']}/panels/{selected['id']}/candidates/{historical['id']}/select",
            json={"expected_version": regenerated["revision"]},
        )
        assert stale_switch.status_code == 409

        other_logical = next(panel for panel in switched_s04["panels"] if panel["id"] != selected["id"])
        mismatched = client.post(
            f"/api/studio/storyboards/{board['id']}/panels/{selected['id']}/candidates/{other_logical['id']}/select",
            json={"expected_version": switched["revision"]},
        )
        assert mismatched.status_code == 409

        switched_history = client.get(
            f"/api/studio/storyboards/{board['id']}/panels/{selected['id']}/candidates"
        )
        assert switched_history.status_code == 200
        assert len(switched_history.json()["candidates"]) == 3
        assert switched_history.json()["candidates"][0]["is_current"] is True

        client.post("/api/auth/logout")
        assert client.post("/api/auth/login", json={"access_code": "code-b"}).status_code == 200
        assert client.get(
            f"/api/studio/storyboards/{board['id']}/panels/{selected['id']}/candidates"
        ).status_code == 404
        assert client.post(
            f"/api/studio/storyboards/{board['id']}/panels/{selected['id']}/candidates/{historical['id']}/select",
            json={"expected_version": switched["revision"]},
        ).status_code == 404
