from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit


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


SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS legacy_storyboard_migrations (
  shot_id TEXT PRIMARY KEY REFERENCES storyboard_shots(id) ON DELETE CASCADE,
  storyboard_id TEXT NOT NULL REFERENCES storyboards(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  reason TEXT,
  migrated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_legacy_storyboard_migrations_board
  ON legacy_storyboard_migrations(storyboard_id, status);
"""


SCHEMA_V5 = """
ALTER TABLE legacy_storyboard_migrations ADD COLUMN contract_version INTEGER NOT NULL DEFAULT 4;
ALTER TABLE legacy_storyboard_migrations ADD COLUMN normalized_at TEXT;
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @staticmethod
    def _legacy_id(namespace: str, value: str) -> str:
        return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _is_sendable_url(value: object) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        parsed = urlsplit(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _legacy_description(description: object, title: object, fallback: str) -> str:
        for value in (description, title):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return fallback

    @staticmethod
    def _normalize_legacy_payload(payload: object, description: str, *, version: int) -> dict[str, object]:
        if not isinstance(payload, dict):
            payload = {}
        normalized = dict(payload)
        defaults: dict[str, object] = {
            "story_function": "历史镜头复核",
            "visual": description,
            "shot_size": "中景",
            "camera_angle": "平视",
            "camera_height": "胸口高度",
            "lens_feel": "自然透视",
            "composition": "主体位于9:16画面中心，前中后景关系清楚",
            "action_start": "动作开始前，主体与产品位置清楚",
            "action_trigger": "主体开始执行镜头动作",
            "action_result": "动作完成且结果清楚可见",
            "camera_move": "固定机位或缓慢推进，保持主体连续",
            "sound": "保留现场环境声与动作音",
            "transition": "按动作结果切入下一镜",
            "stable_truth": ["产品外观", "主体身份", "空间方向"],
            "may_vary": ["自然微表情", "轻微环境变化"],
            "first_failure_cue": "产品外观、动作终点或空间方向异常即回炉",
        }
        for key, value in defaults.items():
            current = normalized.get(key)
            if isinstance(value, list):
                valid = isinstance(current, list) and bool(current) and all(
                    isinstance(item, str) and item.strip() for item in current
                )
            else:
                valid = isinstance(current, str) and bool(current.strip())
            if not valid:
                normalized[key] = value
        normalized["reference_manifest"] = []
        normalized["legacy_migration"] = {"version": version, "source": "v2_storyboard_shot"}
        return normalized

    @classmethod
    def _migrate_legacy_storyboards_v4(cls, conn: sqlite3.Connection, timestamp: str) -> None:
        rows = conn.execute(
            """SELECT sh.*,b.task_id,t.client_id,
            a.client_id source_client_id,a.filename source_filename,a.mime_type source_mime_type,
            a.storage_uri source_storage_uri,a.source_url source_source_url,
            a.byte_size source_byte_size,a.status source_status,a.media_type source_media_type,
            a.deleted_at source_deleted_at
            FROM storyboard_shots sh
            JOIN storyboards b ON b.id=sh.storyboard_id
            JOIN task_runs t ON t.id=b.task_id
            LEFT JOIN assets a ON a.id=sh.image_asset_id
            WHERE NOT EXISTS (
              SELECT 1 FROM storyboard_panels p WHERE p.shot_id=sh.id
            ) ORDER BY sh.storyboard_id,sh.ordinal,sh.id"""
        ).fetchall()
        role_copy = {
            "start": (1, "动作起点", "动作开始前，主体、产品和空间位置清楚可见"),
            "action": (2, "关键动作", "主体执行唯一关键动作，产品触点与动作因果清楚"),
            "result": (3, "可见结果", "动作完成，产品结果稳定且可被观众直接验证"),
        }
        for row in rows:
            shot_id = str(row["id"])
            description = cls._legacy_description(
                row["description"], row["title"], f"历史镜头 {row['ordinal']}",
            )
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            payload = cls._normalize_legacy_payload(payload, description, version=4)

            valid_source = bool(
                row["image_asset_id"]
                and row["source_client_id"] == row["client_id"]
                and row["source_media_type"] == "image"
                and row["source_status"] == "ready"
                and cls._is_sendable_url(row["source_storage_uri"])
                and row["source_deleted_at"] is None
            )
            migration_status = "backfilled" if valid_source else "quarantined"
            clean_id = cls._legacy_id("legacy-clean", shot_id)
            annotated_id = cls._legacy_id("legacy-annotated", shot_id)
            asset_metadata = json.dumps({
                "legacy_migration": "v4", "source_asset_id": row["image_asset_id"],
                "quarantined": not valid_source,
            }, ensure_ascii=False)
            for asset_id, source_type, suffix in (
                (clean_id, "storyboard_clean", "clean"),
                (annotated_id, "storyboard_annotated", "annotated"),
            ):
                conn.execute(
                    """INSERT OR IGNORE INTO assets(
                    id,client_id,source_type,media_type,filename,mime_type,storage_uri,source_url,
                    byte_size,sha256,status,metadata_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,NULL,?,?,?,?)""",
                    (
                        asset_id, row["client_id"], source_type, "image",
                        f"legacy-{shot_id}-{suffix}.png", row["source_mime_type"] or "image/png",
                        row["source_storage_uri"] if valid_source else None,
                        row["source_source_url"] if valid_source else None,
                        row["source_byte_size"] if valid_source else None,
                        "ready" if valid_source else "missing", asset_metadata, timestamp, timestamp,
                    ),
                )
            shot_status = row["status"] if valid_source else "legacy_incomplete"
            conn.execute(
                """UPDATE storyboard_shots SET description=?,image_asset_id=?,status=?,payload_json=?
                WHERE id=?""",
                (description, clean_id, shot_status, json.dumps(payload, ensure_ascii=False), shot_id),
            )
            for role, (ordinal, label, panel_description) in role_copy.items():
                panel_id = cls._legacy_id(f"legacy-panel-{role}", shot_id)
                conn.execute(
                    """INSERT INTO storyboard_panels(
                    id,storyboard_id,shot_id,logical_key,ordinal,revision,role,required,description,
                    annotation_json,annotated_asset_id,clean_asset_id,selected_asset_id,send_to_provider,
                    status,metadata_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,1,?,1,?,?,?,?,?,1,?,?,?,?)""",
                    (
                        panel_id, row["storyboard_id"], shot_id, role, ordinal, role,
                        panel_description, json.dumps({"label": label, "legacy": True}, ensure_ascii=False),
                        annotated_id, clean_id, clean_id,
                        "draft" if valid_source else "legacy_incomplete",
                        json.dumps({"legacy_migration": "v4"}, ensure_ascii=False), timestamp, timestamp,
                    ),
                )
            if not valid_source:
                conn.execute(
                    "UPDATE storyboards SET status='legacy_incomplete',updated_at=? WHERE id=?",
                    (timestamp, row["storyboard_id"]),
                )
            conn.execute(
                """INSERT INTO legacy_storyboard_migrations(
                shot_id,storyboard_id,status,reason,migrated_at
                ) VALUES(?,?,?,?,?)""",
                (
                    shot_id, row["storyboard_id"], migration_status,
                    None if valid_source else "legacy shot has no ready tenant-owned image",
                    timestamp,
                ),
            )

    @classmethod
    def _normalize_legacy_storyboards_v5(cls, conn: sqlite3.Connection, timestamp: str) -> None:
        rows = conn.execute(
            """SELECT sh.id,sh.storyboard_id,sh.title,sh.description,sh.payload_json,sh.image_asset_id,
            t.client_id,a.client_id asset_client_id,a.source_type asset_source_type,
            a.media_type asset_media_type,a.status asset_status,a.storage_uri asset_storage_uri,
            a.deleted_at asset_deleted_at
            FROM storyboard_shots sh
            JOIN legacy_storyboard_migrations migration ON migration.shot_id=sh.id
            JOIN storyboards board ON board.id=sh.storyboard_id
            JOIN task_runs t ON t.id=board.task_id
            LEFT JOIN assets a ON a.id=sh.image_asset_id
            ORDER BY sh.id"""
        ).fetchall()
        for row in rows:
            description = cls._legacy_description(row["description"], row["title"], "历史镜头")
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            normalized = cls._normalize_legacy_payload(payload, description, version=5)
            conn.execute(
                "UPDATE storyboard_shots SET description=?,payload_json=? WHERE id=?",
                (description, json.dumps(normalized, ensure_ascii=False), row["id"]),
            )
            usable = bool(
                row["image_asset_id"]
                and row["asset_client_id"] == row["client_id"]
                and row["asset_source_type"] == "storyboard_clean"
                and row["asset_media_type"] == "image"
                and row["asset_status"] == "ready"
                and cls._is_sendable_url(row["asset_storage_uri"])
                and row["asset_deleted_at"] is None
            )
            if not usable:
                conn.execute(
                    "UPDATE storyboard_shots SET status='legacy_incomplete' WHERE id=?", (row["id"],),
                )
                conn.execute(
                    "UPDATE storyboards SET status='legacy_incomplete',updated_at=? WHERE id=?",
                    (timestamp, row["storyboard_id"]),
                )
                conn.execute(
                    """UPDATE storyboard_panels SET status='legacy_incomplete',updated_at=?
                    WHERE shot_id=?""", (timestamp, row["id"]),
                )
                conn.execute(
                    """UPDATE assets SET status='missing',updated_at=? WHERE id IN (
                    SELECT clean_asset_id FROM storyboard_panels WHERE shot_id=?
                    UNION SELECT annotated_asset_id FROM storyboard_panels WHERE shot_id=?
                    )""", (timestamp, row["id"], row["id"]),
                )
            conn.execute(
                """UPDATE legacy_storyboard_migrations
                SET contract_version=5,normalized_at=?,status=?,reason=? WHERE shot_id=?""",
                (
                    timestamp, "backfilled" if usable else "quarantined",
                    None if usable else "legacy shot has no sendable tenant-owned image",
                    row["id"],
                ),
            )

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
                applied.add(3)
            if 4 not in applied:
                try:
                    conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA_V4)
                    self._migrate_legacy_storyboards_v4(conn, now)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES(4, ?)", (now,),
                    )
                    conn.execute("PRAGMA user_version=4")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                applied.add(4)
            if 5 not in applied:
                try:
                    conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA_V5)
                    self._normalize_legacy_storyboards_v5(conn, now)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES(5, ?)", (now,),
                    )
                    conn.execute("PRAGMA user_version=5")
                    conn.commit()
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

