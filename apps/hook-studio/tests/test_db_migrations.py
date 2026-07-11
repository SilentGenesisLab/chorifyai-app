import json
import sqlite3

from app.db import Database, SCHEMA, SCHEMA_V2


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
        "approval_decisions", "legacy_storyboard_migrations",
    }.issubset(tables)
    assert versions == [1, 2, 3, 4]
    assert db.schema_version() == user_version == 4
    assert job["prompt_user"] == "旧提示"
    assert foreign_key_errors == []


def test_v2_storyboards_backfill_full_contract_panels_and_quarantine_missing_media(tmp_path):
    path = tmp_path / "legacy-v2.sqlite3"
    timestamp = "2026-07-10T01:00:00+00:00"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_migrations VALUES(1,?)", (timestamp,))
        conn.executescript(SCHEMA_V2)
        conn.execute("INSERT INTO schema_migrations VALUES(2,?)", (timestamp,))
        conn.execute("PRAGMA user_version=2")
        conn.execute(
            "INSERT INTO conversations(id,client_id,title,status,created_at,updated_at) VALUES('c1','client-1','旧故事板','active',?,?)",
            (timestamp, timestamp),
        )
        conn.execute(
            """INSERT INTO task_runs(id,client_id,conversation_id,kind,title,status,stage,params_json,
            result_json,created_at,updated_at) VALUES('t1','client-1','c1','create','旧视频','waiting_approval',
            'storyboard_review','{}','{}',?,?)""",
            (timestamp, timestamp),
        )
        conn.execute(
            """INSERT INTO assets(id,client_id,source_type,media_type,filename,mime_type,storage_uri,
            status,metadata_json,created_at,updated_at) VALUES(
            'old-image','client-1','generated','image','old.png','image/png','https://cdn.example/old.png',
            'ready','{}',?,?)""",
            (timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO storyboards(id,task_id,version,status,summary,created_at) VALUES('b1','t1',1,'waiting_approval','旧板',?)",
            (timestamp,),
        )
        conn.execute(
            """INSERT INTO storyboard_shots(id,storyboard_id,ordinal,title,description,duration_seconds,
            image_asset_id,status,payload_json) VALUES('s1','b1',1,'旧镜头','旧描述',5,'old-image','draft',?)""",
            (json.dumps({"visual": "只保留过旧画面字段"}, ensure_ascii=False),),
        )
        conn.execute(
            """INSERT INTO storyboard_shots(id,storyboard_id,ordinal,title,description,duration_seconds,
            image_asset_id,status,payload_json) VALUES('s2','b1',2,'缺图镜头','仍需可读',5,NULL,'draft','{}')"""
        )

    db = Database(path)
    db.initialize()
    db.initialize()

    with db.transaction() as conn:
        versions = [row["version"] for row in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()]
        shots = conn.execute(
            "SELECT id,status,image_asset_id,payload_json FROM storyboard_shots ORDER BY ordinal"
        ).fetchall()
        panels = conn.execute(
            "SELECT * FROM storyboard_panels ORDER BY shot_id,ordinal"
        ).fetchall()
        assets = {row["id"]: row for row in conn.execute(
            "SELECT * FROM assets WHERE source_type IN ('storyboard_clean','storyboard_annotated')"
        ).fetchall()}
        audit = {row["shot_id"]: row for row in conn.execute(
            "SELECT * FROM legacy_storyboard_migrations ORDER BY shot_id"
        ).fetchall()}
        board = conn.execute("SELECT status FROM storyboards WHERE id='b1'").fetchone()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()

    assert versions == [1, 2, 3, 4]
    assert len(panels) == 6
    for shot in shots:
        shot_panels = [panel for panel in panels if panel["shot_id"] == shot["id"]]
        assert [panel["role"] for panel in shot_panels] == ["start", "action", "result"]
        assert all(panel["required"] and panel["selected_asset_id"] for panel in shot_panels)
        assert all(panel["annotated_asset_id"] != panel["selected_asset_id"] for panel in shot_panels)
        payload = json.loads(shot["payload_json"])
        for field in (
            "story_function", "visual", "shot_size", "camera_angle", "camera_height", "lens_feel",
            "composition", "action_start", "action_trigger", "action_result", "camera_move", "sound",
            "transition", "first_failure_cue",
        ):
            assert payload[field]
        assert payload["stable_truth"] and payload["may_vary"]
        assert payload["reference_manifest"] == []
    valid_clean = assets[next(panel["selected_asset_id"] for panel in panels if panel["shot_id"] == "s1")]
    missing_clean = assets[next(panel["selected_asset_id"] for panel in panels if panel["shot_id"] == "s2")]
    assert valid_clean["status"] == "ready" and valid_clean["storage_uri"] == "https://cdn.example/old.png"
    assert missing_clean["status"] == "missing" and missing_clean["storage_uri"] is None
    assert audit["s1"]["status"] == "backfilled"
    assert audit["s2"]["status"] == "quarantined"
    assert board["status"] == "legacy_incomplete"
    assert integrity == "ok"
    assert foreign_key_errors == []
