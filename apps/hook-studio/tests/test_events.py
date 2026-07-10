import json
from datetime import datetime, timezone

from app.db import Database
from app.events import EventWriter
from app.models import EventAction, EventRecord, Mode


def test_event_is_written_to_sqlite_and_jsonl(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    path = tmp_path / "events.jsonl"
    event = EventRecord(
        ts=datetime(2026, 7, 10, tzinfo=timezone.utc), access_code="code-id-1",
        mode=Mode.VIDEO, preset_id="pain-point", template_version="1.0.0",
        prompt_user="一款钱包", prompt_final="完整提示词", params={"duration": 5},
        model="provider-internal", result_url="https://example.invalid/result.mp4",
        latency_ms=1200, cost_units=1, action=EventAction.GENERATE, job_id="job-1",
        client_id="code-id-1", queue_name="video", queue_wait_ms=30,
        provider_attempt=1, skill_trace={"version": "1.0.0"}, error_code=None,
    )
    event_id = EventWriter(db, path).write(event)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    line = json.loads(path.read_text(encoding="utf-8"))
    assert row["access_code"] == "code-id-1"
    assert json.loads(row["params_json"])["duration"] == 5
    assert line["event_id"] == event_id
    assert line["skill_trace"]["version"] == "1.0.0"


def test_event_writer_appends(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    path = tmp_path / "events.jsonl"
    writer = EventWriter(db, path)
    base = dict(
        ts=datetime.now(timezone.utc), access_code="code-id-1", mode=Mode.IMAGE,
        preset_id="contrast", template_version="1.0.0", prompt_user="产品",
        prompt_final="提示词", model="internal", cost_units=0, client_id="code-id-1",
        queue_name="image",
    )
    writer.write(EventRecord(**base, action=EventAction.GENERATE, job_id="job-1"))
    writer.write(EventRecord(**base, action=EventAction.DOWNLOAD, job_id="job-1"))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2

