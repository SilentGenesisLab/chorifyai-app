from __future__ import annotations

import base64
import time

import yaml
from fastapi.testclient import TestClient

from app.main import app
from app.providers.kernel import ProviderResult


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
        assert messages[-1]["assets"][0]["role"] == "final"
        usage = client.get("/api/studio/bootstrap").json()["usage"]
        assert usage["image_used"] == 1
        with app.state.db.transaction() as conn:
            assert conn.execute("SELECT COUNT(*) n FROM training_examples").fetchone()["n"] == 1


def test_image_edit_keeps_contract_versions_and_training_trace(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+Z9er2QAAAABJRU5ErkJggg=="
    )
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "client-code"})
        conversation = client.post("/api/studio/conversations", json={"title": "局部修图"}).json()
        submitted = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages",
            data={"text": "只把选区内的卡片改成绿色，其他像素保持不变", "tool": "edit_image", "links": "[]"},
            files=[
                ("attachments", ("source-face-mask-product.png", png, "image/png")),
                ("attachments", ("mask-selection.png", png, "image/png")),
            ],
        )
        assert submitted.status_code == 202
        task = _wait_task(client, submitted.json()["task"]["id"], {"succeeded", "failed"})
        assert task["status"] == "succeeded"
        assert task["result"]["route"] == "direct_edit"

        messages = client.get(f"/api/studio/conversations/{conversation['id']}/messages").json()["items"]
        assert messages[-1]["kind"] == "media"
        assert messages[-1]["assets"][0]["type"] == "image"
        with app.state.db.transaction() as conn:
            contract = conn.execute(
                "SELECT * FROM image_edit_contracts WHERE task_id=?", (task["id"],),
            ).fetchone()
            versions = conn.execute(
                "SELECT relation,selected FROM asset_versions WHERE edit_contract_id=?", (contract["id"],),
            ).fetchall()
            skill = conn.execute(
                "SELECT skill_id,status FROM skill_runs WHERE task_id=?", (task["id"],),
            ).fetchone()
            training = conn.execute(
                "SELECT COUNT(*) n FROM training_examples WHERE task_id=?", (task["id"],),
            ).fetchone()["n"]
        assert contract["status"] == "completed"
        assert [(row["relation"], row["selected"]) for row in versions] == [("selected", 1)]
        assert skill["skill_id"] == "hook-studio-image-router"
        assert skill["status"] == "passed"
        assert training == 1


def test_image_edit_enforces_mask_composite_when_kernel_does_not(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+Z9er2QAAAABJRU5ErkJggg=="
    )
    composite_calls = []

    async def edit_without_composite(self, **kwargs):
        return ProviderResult(
            "success", "https://placehold.co/720x1280/png?text=Raw", "raw-edit",
            trace={"provider": "fake", "composite_applied": False},
        )

    async def fake_composite(source_url, edited_url, mask_url):
        composite_calls.append((source_url, edited_url, mask_url))
        return png

    monkeypatch.setattr("app.providers.fake.FakeKernelProvider.edit_image", edit_without_composite)
    monkeypatch.setattr("app.services.production.composite_masked_image_file", fake_composite)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "client-code"})
        conversation = client.post("/api/studio/conversations", json={"title": "强制合成"}).json()
        submitted = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages",
            data={"text": "只修改蒙版内颜色", "tool": "edit_image", "links": "[]"},
            files=[
                ("attachments", ("source-face-mask-product.png", png, "image/png")),
                ("attachments", ("mask-selection.png", png, "image/png")),
            ],
        ).json()
        task = _wait_task(client, submitted["task"]["id"], {"succeeded", "failed"})
        assert task["status"] == "succeeded"
        assert task["result"]["route"] == "direct_edit+mask_pixel_composite"
        assert len(composite_calls) == 1
        with app.state.db.transaction() as conn:
            version = conn.execute(
                "SELECT qc_json FROM asset_versions WHERE selected=1",
            ).fetchone()
        assert '"outside_mask_preserved": true' in version["qc_json"].lower()


def test_image_edit_falls_back_to_reference_repaint(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+Z9er2QAAAABJRU5ErkJggg=="
    )

    async def rejected_edit(self, **kwargs):
        raise RuntimeError("edit endpoint unavailable")

    async def fake_composite(source_url, edited_url, mask_url):
        return png

    monkeypatch.setattr("app.providers.fake.FakeKernelProvider.edit_image", rejected_edit)
    monkeypatch.setattr("app.services.production.composite_masked_image_file", fake_composite)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"access_code": "client-code"})
        conversation = client.post("/api/studio/conversations", json={"title": "降级链"}).json()
        submitted = client.post(
            f"/api/studio/conversations/{conversation['id']}/messages",
            data={"text": "只修改选区颜色", "tool": "edit_image", "links": "[]"},
            files=[
                ("attachments", ("source-product.png", png, "image/png")),
                ("attachments", ("mask-selection.png", png, "image/png")),
                ("attachments", ("annotation-location.png", png, "image/png")),
            ],
        ).json()
        task = _wait_task(client, submitted["task"]["id"], {"succeeded", "failed"})
        assert task["status"] == "succeeded"
        assert task["result"]["route"] == "reference_repaint+mask_pixel_composite"
        contract = app.state.workspace.get_task(task["id"])["params"]["image_contract"]
        assert "图2只作为annotation" in contract["prompt_final"]
        assert "图3" not in contract["prompt_final"]


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
