from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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


SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_client_updated
  ON conversations(client_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id),
  seq INTEGER NOT NULL,
  role TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'text',
  content_text TEXT,
  content_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'complete',
  reply_to_message_id TEXT REFERENCES messages(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(conversation_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_seq
  ON messages(conversation_id, seq);

CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  media_type TEXT NOT NULL,
  filename TEXT,
  mime_type TEXT,
  storage_uri TEXT,
  source_url TEXT,
  byte_size INTEGER,
  sha256 TEXT,
  status TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_assets_client_created
  ON assets(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON assets(client_id, sha256);

CREATE TABLE IF NOT EXISTS message_assets (
  message_id TEXT NOT NULL REFERENCES messages(id),
  asset_id TEXT NOT NULL REFERENCES assets(id),
  usage TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  caption TEXT,
  PRIMARY KEY(message_id, asset_id, usage),
  UNIQUE(message_id, usage, ordinal)
);

CREATE TABLE IF NOT EXISTS asset_extractions (
  id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets(id),
  parser_name TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  status TEXT NOT NULL,
  text_content TEXT,
  structured_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  UNIQUE(asset_id, parser_name, parser_version)
);

CREATE TABLE IF NOT EXISTS asset_segments (
  id TEXT PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES asset_extractions(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  page_no INTEGER,
  start_ms INTEGER,
  end_ms INTEGER,
  speaker TEXT,
  text_content TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(extraction_id, ordinal)
);

CREATE TABLE IF NOT EXISTS task_runs (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL REFERENCES conversations(id),
  request_message_id TEXT REFERENCES messages(id),
  result_message_id TEXT REFERENCES messages(id),
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  params_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT,
  error_message TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_task_runs_client_updated
  ON task_runs(client_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_runs_conversation_updated
  ON task_runs(conversation_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS task_jobs (
  task_id TEXT NOT NULL REFERENCES task_runs(id),
  job_id TEXT NOT NULL REFERENCES jobs(id),
  role TEXT NOT NULL DEFAULT 'primary',
  ordinal INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(task_id, job_id),
  UNIQUE(task_id, role, ordinal)
);

CREATE TABLE IF NOT EXISTS storyboards (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES task_runs(id),
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  summary TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(task_id, version)
);

CREATE TABLE IF NOT EXISTS storyboard_shots (
  id TEXT PRIMARY KEY,
  storyboard_id TEXT NOT NULL REFERENCES storyboards(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  title TEXT,
  description TEXT,
  duration_seconds REAL,
  image_asset_id TEXT REFERENCES assets(id),
  status TEXT NOT NULL DEFAULT 'draft',
  payload_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(storyboard_id, ordinal)
);

CREATE TABLE IF NOT EXISTS activity_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  client_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  conversation_id TEXT REFERENCES conversations(id),
  message_id TEXT REFERENCES messages(id),
  task_id TEXT REFERENCES task_runs(id),
  asset_id TEXT REFERENCES assets(id),
  dedupe_key TEXT UNIQUE,
  payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_activity_events_client_ts
  ON activity_events(client_id, ts);

CREATE TABLE IF NOT EXISTS training_examples (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL REFERENCES conversations(id),
  input_message_id TEXT REFERENCES messages(id),
  output_message_id TEXT REFERENCES messages(id),
  task_id TEXT REFERENCES task_runs(id),
  schema_version INTEGER NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT NOT NULL,
  labels_json TEXT NOT NULL DEFAULT '{}',
  quality_json TEXT NOT NULL DEFAULT '{}',
  eligibility TEXT NOT NULL DEFAULT 'eligible',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_training_examples_client_created
  ON training_examples(client_id, created_at);

CREATE TABLE IF NOT EXISTS quota_ledger (
  id TEXT PRIMARY KEY,
  day_cn TEXT NOT NULL,
  client_id TEXT NOT NULL,
  resource TEXT NOT NULL,
  units INTEGER NOT NULL CHECK(units > 0),
  state TEXT NOT NULL,
  task_id TEXT REFERENCES task_runs(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  committed_at TEXT,
  released_at TEXT,
  UNIQUE(task_id, resource)
);
CREATE INDEX IF NOT EXISTS idx_quota_ledger_day_resource
  ON quota_ledger(day_cn, resource, state);
CREATE INDEX IF NOT EXISTS idx_quota_ledger_client_day
  ON quota_ledger(client_id, day_cn, resource, state);
"""


SCHEMA_V3 = """
ALTER TABLE storyboards ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE storyboards ADD COLUMN updated_at TEXT;
ALTER TABLE storyboards ADD COLUMN animatic_asset_id TEXT REFERENCES assets(id);
ALTER TABLE storyboards ADD COLUMN animatic_status TEXT NOT NULL DEFAULT 'missing';
ALTER TABLE storyboards ADD COLUMN animatic_confirmed_at TEXT;
ALTER TABLE storyboards ADD COLUMN frozen_snapshot_hash TEXT;
ALTER TABLE storyboard_shots ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;

UPDATE storyboards SET updated_at=created_at WHERE updated_at IS NULL;

CREATE TABLE IF NOT EXISTS storyboard_panels (
  id TEXT PRIMARY KEY,
  storyboard_id TEXT NOT NULL REFERENCES storyboards(id) ON DELETE CASCADE,
  shot_id TEXT NOT NULL REFERENCES storyboard_shots(id) ON DELETE CASCADE,
  logical_key TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  role TEXT NOT NULL,
  required INTEGER NOT NULL DEFAULT 1,
  description TEXT NOT NULL DEFAULT '',
  annotation_json TEXT NOT NULL DEFAULT '{}',
  annotated_asset_id TEXT REFERENCES assets(id),
  clean_asset_id TEXT REFERENCES assets(id),
  selected_asset_id TEXT REFERENCES assets(id),
  send_to_provider INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  superseded_at TEXT,
  UNIQUE(shot_id, logical_key, revision)
);
CREATE INDEX IF NOT EXISTS idx_storyboard_panels_shot_current
  ON storyboard_panels(shot_id, logical_key, revision DESC);
CREATE INDEX IF NOT EXISTS idx_storyboard_panels_board
  ON storyboard_panels(storyboard_id, ordinal);

CREATE TABLE IF NOT EXISTS skill_runs (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES task_runs(id),
  storyboard_id TEXT REFERENCES storyboards(id),
  shot_id TEXT REFERENCES storyboard_shots(id),
  skill_id TEXT NOT NULL,
  skill_version TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  blocking INTEGER NOT NULL DEFAULT 0,
  public_label TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  output_hash TEXT NOT NULL,
  input_count INTEGER NOT NULL DEFAULT 0,
  output_count INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  retry_count INTEGER NOT NULL DEFAULT 0,
  blocking_reason TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  private_trace_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_runs_task_created ON skill_runs(task_id, created_at, id);

CREATE TABLE IF NOT EXISTS workflow_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES task_runs(id),
  client_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workflow_events_task_id ON workflow_events(task_id, id);
CREATE INDEX IF NOT EXISTS idx_workflow_events_client_id ON workflow_events(client_id, id);

CREATE TABLE IF NOT EXISTS approval_decisions (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES task_runs(id),
  storyboard_id TEXT NOT NULL REFERENCES storyboards(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  target_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  feedback TEXT NOT NULL DEFAULT '',
  expected_version INTEGER NOT NULL,
  target_revision INTEGER NOT NULL,
  snapshot_hash TEXT,
  idempotency_key TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(client_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_approval_decisions_board_created
  ON approval_decisions(storyboard_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_approval_decisions_target
  ON approval_decisions(scope, target_id, created_at, id);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                )"""
            )
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
                (now,),
            )
            applied = {
                int(row["version"])
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            if 2 not in applied:
                try:
                    conn.executescript(
                        "BEGIN IMMEDIATE;\n"
                        + SCHEMA_V2
                        + "\nINSERT INTO schema_migrations(version, applied_at) "
                        "VALUES(2, strftime('%Y-%m-%dT%H:%M:%fZ','now'));\n"
                        "PRAGMA user_version=2;\nCOMMIT;"
                    )
                except Exception:
                    conn.rollback()
                    raise
                applied.add(2)
            if 3 not in applied:
                try:
                    conn.executescript(
                        "BEGIN IMMEDIATE;\n"
                        + SCHEMA_V3
                        + "\nINSERT INTO schema_migrations(version, applied_at) "
                        "VALUES(3, strftime('%Y-%m-%dT%H:%M:%fZ','now'));\n"
                        "PRAGMA user_version=3;\nCOMMIT;"
                    )
                except Exception:
                    conn.rollback()
                    raise

    def schema_version(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        return int(row["version"] or 0) if row else 0

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

