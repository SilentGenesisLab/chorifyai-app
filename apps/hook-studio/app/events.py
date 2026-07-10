from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.db import Database
from app.models import EventRecord


class EventWriter:
    """Persist events to SQLite and an append-only JSONL stream.

    SQLite is committed first. JSONL failures are surfaced so callers can alert and retry;
    the database remains the authoritative export source for reconciliation.
    """

    def __init__(self, db: Database, jsonl_path: Path | str):
        self.db = db
        self.jsonl_path = Path(jsonl_path)
        self._lock = threading.Lock()

    def write(self, event: EventRecord) -> int:
        data = event.model_dump(mode="json")
        with self.db.transaction(immediate=True) as conn:
            cursor = conn.execute(
                """INSERT INTO events(
                  ts, access_code, mode, preset_id, template_version, prompt_user, prompt_final,
                  params_json, model, result_url, latency_ms, cost_units, action, job_id, client_id,
                  queue_name, queue_wait_ms, provider_attempt, skill_trace_json, error_code
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data["ts"], data["access_code"], data["mode"], data["preset_id"],
                    data["template_version"], data["prompt_user"], data["prompt_final"],
                    json.dumps(data["params"], ensure_ascii=False, separators=(",", ":")),
                    data["model"], data["result_url"], data["latency_ms"], data["cost_units"],
                    data["action"], data["job_id"], data["client_id"], data["queue_name"],
                    data["queue_wait_ms"], data["provider_attempt"],
                    json.dumps(data["skill_trace"], ensure_ascii=False, separators=(",", ":")) if data["skill_trace"] is not None else None,
                    data["error_code"],
                ),
            )
            event_id = int(cursor.lastrowid)
        line = json.dumps({"event_id": event_id, **data}, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.jsonl_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        return event_id

