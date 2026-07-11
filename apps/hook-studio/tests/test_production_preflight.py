from __future__ import annotations

import time
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.main import app


def _configure(monkeypatch, tmp_path):
    codes = tmp_path / "access_codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [
        {"id": "client-a", "code": "code-a", "client_name": "A", "role": "client",
         "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True},
        {"id": "client-b", "code": "code-b", "client_name": "B", "role": "client",
         "daily_video_limit": 100, "daily_image_limit": 1000, "enabled": True},
    ]}), encoding="utf-8")
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/")
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", str(codes))
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("HOOK_STUDIO_PROVIDER_MODE", "fake")


def _wait_for_board(client: TestClient, task_id: str) -> None:
    for _ in range(200):
        task = client.get(f"/api/studio/tasks/{task_id}").json()
        if task["status"] == "waiting_confirmation":
            return
        if task["status"] == "failed":
            raise AssertionError(task)
        time.sleep(0.01)
    raise AssertionError("task did not produce storyboard")


def _create_board(client: TestClient) -> dict[str, Any]:
    conversation = client.post("/api/studio/conversations", json={"title": "preflight"}).json()
    submitted = client.post(
        f"/api/studio/conversations/{conversation['id']}/messages",
        data={"text": "制作8秒产品视频", "tool": "create_video",
              "duration_seconds": "8", "links": "[]"},
    ).json()
    _wait_for_board(client, submitted["task"]["id"])
    messages = client.get(
        f"/api/studio/conversations/{conversation['id']}/messages",
    ).json()["items"]
    storyboard_id = next(
        item["storyboard"]["id"] for item in messages if item["kind"] == "storyboard"
    )
    return client.get(f"/api/studio/storyboards/{storyboard_id}").json()


def _approve_and_confirm_animatic(client: TestClient, board: dict[str, Any]) -> dict[str, Any]:
    for shot in board["shots"]:
        for panel in shot["panels"]:
            response = client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
                "expected_version": board["revision"], "scope": "panel",
                "target_id": panel["id"], "decision": "approved", "feedback": "通过",
            })
            assert response.status_code == 200, response.text
        response = client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
            "expected_version": board["revision"], "scope": "shot",
            "target_id": shot["id"], "decision": "approved", "feedback": "通过",
        })
        assert response.status_code == 200, response.text
    response = client.post(f"/api/studio/storyboards/{board['id']}/decisions", json={
        "expected_version": board["revision"], "scope": "board",
        "target_id": board["id"], "decision": "approved", "feedback": "通过",
    })
    assert response.status_code == 200, response.text
    animatic = client.post(f"/api/studio/storyboards/{board['id']}/animatic", json={
        "expected_version": board["revision"], "confirm": True,
    })
    assert animatic.status_code == 200, animatic.text
    return animatic.json()


def _public_keys(value: Any) -> set[str]:
    if isinstance(value, list):
        return set().union(*(_public_keys(item) for item in value), set())
    if not isinstance(value, dict):
        return set()
    return {str(key).lower() for key in value} | set().union(
        *(_public_keys(item) for item in value.values()), set(),
    )


def _assert_no_video_reservation_or_submit(client: TestClient, submit_calls: list[dict[str, Any]]) -> None:
    with client.app.state.workspace.db.transaction() as conn:
        video_rows = conn.execute(
            "SELECT COUNT(*) FROM quota_ledger WHERE resource='video'",
        ).fetchone()[0]
    assert video_rows == 0
    assert submit_calls == []
    assert client.get("/api/studio/bootstrap").json()["usage"]["client_video_used"] == 0


def test_invalid_manifest_is_422_before_quota_and_internal_fields_are_not_public(
    monkeypatch, tmp_path,
):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"access_code": "code-a"}).status_code == 200
        board = _create_board(client)
        foreign = client.app.state.workspace.create_asset(
            client_id="client-b", source_type="upload", media_type="image",
            storage_uri="https://cdn.example/foreign-reference.png", status="ready",
        )
        assert foreign["client_id"] == "client-b"
        patched = client.patch(
            f"/api/studio/storyboards/{board['id']}/shots/{board['shots'][0]['id']}",
            json={
                "expected_version": board["revision"],
                "reference_manifest": [{
                    "kind": "image", "slot": 1, "url": foreign["storage_uri"],
                    "role": "主体身份", "controls": ["外观"],
                    "must_not_control": ["运镜"], "provider": "SecretProvider",
                    "model": "SecretModel",
                }],
            },
        )
        assert patched.status_code == 200, patched.text
        board = patched.json()
        assert not any(
            "provider" in key or key.startswith("model") for key in _public_keys(board)
        )
        assert "SecretProvider" not in client.get(
            f"/api/studio/storyboards/{board['id']}",
        ).text
        _approve_and_confirm_animatic(client, board)

        submit_calls: list[dict[str, Any]] = []
        original_submit = client.app.state.production.provider.submit_video

        async def submit_spy(**kwargs):
            submit_calls.append(kwargs)
            return await original_submit(**kwargs)

        monkeypatch.setattr(client.app.state.production.provider, "submit_video", submit_spy)
        produced = client.post(
            f"/api/studio/storyboards/{board['id']}/produce",
            json={"expected_version": board["revision"]},
        )
        assert produced.status_code == 422, produced.text
        assert "SecretProvider" not in produced.text
        assert "SecretModel" not in produced.text
        _assert_no_video_reservation_or_submit(client, submit_calls)


def test_unreadable_or_unready_selected_clean_frame_is_422_before_quota(
    monkeypatch, tmp_path,
):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"access_code": "code-a"}).status_code == 200
        board = _create_board(client)
        _approve_and_confirm_animatic(client, board)
        selected_ids = [
            panel["selected_asset_id"] for shot in board["shots"] for panel in shot["panels"]
        ]
        with client.app.state.workspace.db.transaction(immediate=True) as conn:
            conn.execute("UPDATE assets SET storage_uri=NULL WHERE id=?", (selected_ids[0],))
            conn.execute("UPDATE assets SET status='failed' WHERE id=?", (selected_ids[1],))

        submit_calls: list[dict[str, Any]] = []
        original_submit = client.app.state.production.provider.submit_video

        async def submit_spy(**kwargs):
            submit_calls.append(kwargs)
            return await original_submit(**kwargs)

        monkeypatch.setattr(client.app.state.production.provider, "submit_video", submit_spy)
        produced = client.post(
            f"/api/studio/storyboards/{board['id']}/produce",
            json={"expected_version": board["revision"]},
        )
        assert produced.status_code == 422, produced.text
        _assert_no_video_reservation_or_submit(client, submit_calls)
