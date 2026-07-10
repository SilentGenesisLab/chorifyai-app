from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, client_id TEXT NOT NULL, mode TEXT NOT NULL,
  preset_id TEXT NOT NULL, template_version TEXT NOT NULL,
  prompt_user TEXT NOT NULL, prompt_final TEXT NOT NULL, params_json TEXT NOT NULL,
  model TEXT NOT NULL, status TEXT NOT NULL, queue_name TEXT NOT NULL,
  provider_job_id TEXT, result_url TEXT, result_meta_json TEXT,
  skill_trace_json TEXT, error_code TEXT, error_message TEXT, retry_count INTEGER NOT NULL DEFAULT 0,
  queued_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, deleted_at TEXT, parent_job_id TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, access_code TEXT NOT NULL,
  mode TEXT NOT NULL, preset_id TEXT NOT NULL, template_version TEXT NOT NULL,
  prompt_user TEXT NOT NULL, prompt_final TEXT NOT NULL, params_json TEXT NOT NULL,
  model TEXT NOT NULL, result_url TEXT, latency_ms INTEGER, cost_units INTEGER NOT NULL,
  action TEXT NOT NULL, job_id TEXT NOT NULL, client_id TEXT NOT NULL,
  queue_name TEXT NOT NULL, queue_wait_ms INTEGER, provider_attempt INTEGER,
  skill_trace_json TEXT, error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_client_ts ON events(client_id, ts);

CREATE TABLE IF NOT EXISTS daily_usage (
  day_cn TEXT NOT NULL, client_id TEXT NOT NULL, video_reserved INTEGER NOT NULL DEFAULT 0,
  video_succeeded INTEGER NOT NULL DEFAULT 0, video_failed INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL, PRIMARY KEY(day_cn, client_id)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

