from __future__ import annotations

import time

import yaml
from fastapi.testclient import TestClient

from app.main import app


def _configure(monkeypatch, tmp_path):
    codes = tmp_path / "access_codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [
        {"id": "client-01", "code": "client-code", "client_name": "测试客户", "role": "client", "daily_video_limit": 10, "enabled": True},
        {"id": "admin-primary", "code": "admin-code", "client_name": "管理员", "role": "admin", "daily_video_limit": 100, "enabled": True},
    ]}, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/")
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", str(codes))
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("HOOK_STUDIO_PROVIDER_MODE", "fake")


def _wait_for_success(client: TestClient, job_id: str) -> dict:
    for _ in range(50):
        payload = client.get(f"/api/studio/jobs/{job_id}").json()
        if payload["job"]["status"] in {"succeeded", "failed"}:
            return payload["job"]
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_protected_flow_and_independent_modes(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/studio/bootstrap").status_code == 401
        login = client.post("/api/auth/login", json={"access_code": "client-code"})
        assert login.status_code == 200
        assert client.get("/api/auth/session").json()["principal"]["code_id"] == "client-01"
        bootstrap = client.get("/api/studio/bootstrap").json()
        assert len(bootstrap["presets"]) == 6
        assert "product-pop" not in {item["id"] for item in bootstrap["presets"]}

        image = client.post("/api/studio/jobs", data={"mode": "image", "preset_id": "pain-point", "prompt_user": "便携桌面灯，触摸开关，照亮键盘"})
        assert image.status_code == 202
        image_job = _wait_for_success(client, image.json()["job"]["id"])
        assert image_job["mode"] == "image" and image_job["result_url"]

        video = client.post("/api/studio/jobs", data={"mode": "video", "preset_id": "handheld-proof", "prompt_user": "便携桌面灯，手指按下触摸开关，随后灯光亮起并照亮键盘", "duration": "5"})
        assert video.status_code == 202
        video_job = _wait_for_success(client, video.json()["job"]["id"])
        assert video_job["mode"] == "video" and video_job["result_meta"]["qc"]["passed"] is True

        queues = client.get("/api/health").json()["queues"]
        assert queues["image"]["concurrency"] == queues["video"]["concurrency"] == 2


def test_admin_dashboard_lists_clients(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"access_code": "admin-code"}).status_code == 200
        dashboard = client.get("/api/admin/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["clients"][0]["id"] == "client-01"
        assert dashboard.json()["usage"]["global_video_limit"] == 100
