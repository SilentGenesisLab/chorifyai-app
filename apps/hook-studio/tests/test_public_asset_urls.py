from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from app.api.workspace import _asset_payload, _public_projection, _sendable_asset_url
from app.main import app


def _configure(monkeypatch, tmp_path) -> None:
    codes = tmp_path / "access_codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [{
        "id": "client-01", "code": "client-code", "client_name": "测试客户",
        "role": "client", "daily_video_limit": 100, "daily_image_limit": 1000,
        "enabled": True,
    }]}), encoding="utf-8")
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/")
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", str(codes))
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("HOOK_STUDIO_PROVIDER_MODE", "fake")


def test_asset_projection_only_exposes_ready_sendable_urls() -> None:
    unsafe = {
        "id": "legacy", "status": "missing", "media_type": "image",
        "storage_uri": "https://user:secret@example.com/private.png",
        "metadata": {"thumbnail_url": "file:///tmp/private.png"},
    }
    assert _sendable_asset_url(unsafe) == ""
    assert _asset_payload(unsafe)["url"] == ""
    assert _asset_payload(unsafe)["thumbnail_url"] == ""

    ready = {
        "id": "ready", "status": "ready", "media_type": "image",
        "storage_uri": "https://cdn.example.com/result.png?version=1", "metadata": {},
    }
    assert _sendable_asset_url(ready) == ready["storage_uri"]
    assert _asset_payload(ready)["thumbnail_url"] == ready["storage_uri"]


def test_nested_task_projection_scrubs_unsafe_urls() -> None:
    projected = _public_projection({
        "result_url": "file:///tmp/result.mp4",
        "thumbnail_url": "https://cdn.example.com/thumb.jpg",
        "video_urls": ["https://cdn.example.com/video.mp4", "https://u:p@example.com/leak.mp4"],
    })
    assert projected["result_url"] == ""
    assert projected["thumbnail_url"] == "https://cdn.example.com/thumb.jpg"
    assert projected["video_urls"] == ["https://cdn.example.com/video.mp4"]


def test_legacy_invalid_asset_cannot_preview_or_download(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"access_code": "client-code"}).status_code == 200
        asset = app.state.workspace.create_asset(
            client_id="client-01", source_type="migration", media_type="image",
            status="missing", filename="legacy.png",
            storage_uri="https://user:secret@example.com/private.png",
        )
        assert client.get(f"/api/studio/assets/{asset['id']}/preview").status_code == 404
        assert client.get(f"/api/studio/assets/{asset['id']}/download").status_code == 404
        response = client.post("/api/studio/assets/batch-download", json={"asset_ids": [asset["id"]]})
        assert response.status_code == 404

