import json
import sqlite3

from app.db import Database, SCHEMA


def test_v1_database_migrates_additively_and_idempotently(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """INSERT INTO jobs(
            id,client_id,mode,preset_id,template_version,prompt_user,prompt_final,
            params_json,model,status,queue_name,queued_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("job-1", "client-1", "image", "pain-point", "1.0.0", "旧提示",
             "旧完整提示", json.dumps({"duration": 4}), "legacy", "succeeded",
             "image", "2026-07-10T01:00:00+00:00"),
        )

    db = Database(path)
    db.initialize()
    db.initialize()

    with db.transaction() as conn:
        tables = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        versions = [row["version"] for row in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()]
        job = conn.execute("SELECT * FROM jobs WHERE id='job-1'").fetchone()
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert {
        "conversations", "messages", "assets", "message_assets", "task_runs",
        "storyboards", "storyboard_shots", "activity_events", "training_examples",
        "quota_ledger", "storyboard_panels", "skill_runs", "workflow_events",
        "approval_decisions",
    }.issubset(tables)
    assert versions == [1, 2, 3]
    assert db.schema_version() == user_version == 3
    assert job["prompt_user"] == "旧提示"
    assert foreign_key_errors == []
