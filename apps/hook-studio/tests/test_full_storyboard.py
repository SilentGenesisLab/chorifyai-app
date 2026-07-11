from __future__ import annotations

from app.db import Database
from app.repositories.workspace import WorkspaceRepository


def _workspace(tmp_path):
    db = Database(tmp_path / "hook.sqlite3")
    db.initialize()
    repo = WorkspaceRepository(db)
    conversation = repo.create_conversation(client_id="client-a", title="board")
    task = repo.create_task(client_id="client-a", conversation_id=conversation["id"], kind="create", title="video")
    clean = repo.create_asset(client_id="client-a", source_type="storyboard", media_type="image", storage_uri="https://x/clean.png")
    board = repo.save_storyboard(task["id"], [{
        "id": "shot-1", "title": "开场", "description": "产品进入画面", "duration_seconds": 5,
        "image_asset_id": clean["id"], "story_function": "建立钩子", "action_start": "空桌面",
        "action_trigger": "手拿产品进入", "action_result": "产品居中", "shot_size": "近景",
        "camera_angle": "平视", "camera_height": "桌面高度", "lens_feel": "35mm",
        "composition": "产品位于中央", "camera_move": "缓慢推近", "sound": "环境音",
        "transition": "硬切", "stable_truth": ["产品外观"], "may_vary": ["手部位置"],
        "reference_manifest": [], "first_failure_cue": "产品结构漂移",
        "panels": [{
            "id": "panel-1", "ordinal": 1, "role": "start", "required": True,
            "description": "动作起点", "clean_asset_id": clean["id"], "selected_asset_id": clean["id"],
            "send_to_provider": True,
        }],
    }], client_id="client-a", status="waiting_approval")
    return db, repo, task, board


def test_v3_migration_and_panel_one_to_many(tmp_path):
    db, repo, task, board = _workspace(tmp_path)
    assert db.schema_version() >= 3
    with db.transaction() as conn:
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"storyboard_panels", "skill_runs", "workflow_events", "approval_decisions"} <= names
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    detail = repo.get_storyboard(board["id"], client_id="client-a")
    assert detail is not None
    assert detail["shots"][0]["panels"][0]["selected_asset_id"]
    assert repo.get_storyboard(board["id"], client_id="client-b") is None


def test_approvals_are_append_only_and_events_replay(tmp_path):
    _, repo, task, board = _workspace(tmp_path)
    first = repo.record_approval(
        storyboard_id=board["id"], client_id="client-a", scope="panel", target_id="panel-1",
        decision="approved", expected_version=1, feedback="ok",
    )
    second = repo.record_approval(
        storyboard_id=board["id"], client_id="client-a", scope="panel", target_id="panel-1",
        decision="revision_required", expected_version=1, feedback="redo",
    )
    assert first["id"] != second["id"]
    assert len(repo.list_approvals(board["id"], client_id="client-a")) == 2
    one = repo.append_workflow_event(task["id"], client_id="client-a", event_type="shot.ready", payload={"shot": 1})
    two = repo.append_workflow_event(task["id"], client_id="client-a", event_type="panel.ready", payload={"panel": 1})
    replay = repo.list_workflow_events(task["id"], client_id="client-a", after_id=one["id"])
    assert [item["id"] for item in replay] == [two["id"]]

