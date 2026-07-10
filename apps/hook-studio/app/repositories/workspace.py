from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from app.db import Database


JSON_FIELDS = {
    "content_json": "content",
    "metadata_json": "metadata",
    "params_json": "params",
    "result_json": "result",
    "payload_json": "payload",
    "structured_json": "structured",
    "input_json": "input",
    "output_json": "output",
    "labels_json": "labels",
    "quality_json": "quality",
}


class WorkspaceError(RuntimeError):
    pass


class WorkspaceNotFound(WorkspaceError):
    pass


class WorkspaceConflict(WorkspaceError):
    pass


class QuotaExceeded(WorkspaceError):
    def __init__(self, message: str, snapshot: dict[str, Any]):
        self.snapshot = snapshot
        super().__init__(message)


def _now(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).isoformat()


def _china_day(value: str | datetime | None = None) -> str:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value[:10]
    else:
        parsed = value or datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _stable_id(kind: str, value: str) -> str:
    return uuid5(NAMESPACE_URL, f"hook-studio:v2:{kind}:{value}").hex


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _decode(row: Any) -> dict[str, Any]:
    result = dict(row)
    for source, target in JSON_FIELDS.items():
        if source in result:
            result[target] = _loads(result.pop(source), {})
    return result


class WorkspaceRepository:
    """SQLite boundary for conversations, assets, tasks, storyboards and quota."""

    def __init__(self, db: Database):
        self.db = db

    def create_conversation(
        self, *, client_id: str, title: str = "新对话", conversation_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        conversation_id = conversation_id or uuid4().hex
        timestamp = _now(now)
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT INTO conversations(
                id,client_id,title,status,created_at,updated_at
                ) VALUES(?,?,?,'active',?,?)""",
                (conversation_id, client_id, title.strip() or "新对话", timestamp, timestamp),
            )
            row = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        return _decode(row)

    def list_conversations(self, client_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        clause = "" if include_deleted else " AND deleted_at IS NULL"
        with self.db.transaction() as conn:
            rows = conn.execute(
                f"SELECT * FROM conversations WHERE client_id=?{clause} ORDER BY updated_at DESC,id",
                (client_id,),
            ).fetchall()
        return [_decode(row) for row in rows]

    def get_conversation(self, conversation_id: str, *, client_id: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM conversations WHERE id=?"
        params: list[Any] = [conversation_id]
        if client_id is not None:
            sql += " AND client_id=?"
            params.append(client_id)
        with self.db.transaction() as conn:
            row = conn.execute(sql, params).fetchone()
        return _decode(row) if row else None

    def delete_conversation(self, conversation_id: str, *, client_id: str) -> bool:
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            cursor = conn.execute(
                """UPDATE conversations SET status='deleted',deleted_at=?,updated_at=?
                WHERE id=? AND client_id=? AND deleted_at IS NULL""",
                (timestamp, timestamp, conversation_id, client_id),
            )
        return cursor.rowcount == 1

    def add_message(
        self, conversation_id: str, *, role: str, content_text: str | None = None,
        kind: str = "text", content: dict[str, Any] | None = None,
        status: str = "complete", reply_to_message_id: str | None = None,
        message_id: str | None = None, client_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        message_id = message_id or uuid4().hex
        timestamp = _now(now)
        with self.db.transaction(immediate=True) as conn:
            conversation = conn.execute(
                "SELECT client_id FROM conversations WHERE id=? AND deleted_at IS NULL",
                (conversation_id,),
            ).fetchone()
            if conversation is None or (client_id is not None and conversation["client_id"] != client_id):
                raise WorkspaceNotFound("conversation not found")
            if reply_to_message_id is not None:
                reply = conn.execute(
                    "SELECT 1 FROM messages WHERE id=? AND conversation_id=?",
                    (reply_to_message_id, conversation_id),
                ).fetchone()
                if reply is None:
                    raise WorkspaceConflict("reply message is outside the conversation")
            seq = int(conn.execute(
                "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM messages WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()["seq"])
            conn.execute(
                """INSERT INTO messages(
                id,conversation_id,seq,role,kind,content_text,content_json,status,
                reply_to_message_id,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (message_id, conversation_id, seq, role, kind, content_text,
                 json.dumps(content or {}, ensure_ascii=False), status,
                 reply_to_message_id, timestamp, timestamp),
            )
            conn.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?", (timestamp, conversation_id),
            )
            row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        return _decode(row)

    def list_messages(
        self, conversation_id: str, *, client_id: str | None = None,
        after_seq: int | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        params: list[Any] = [conversation_id]
        ownership = ""
        if client_id is not None:
            ownership = " AND c.client_id=?"
            params.append(client_id)
        after = ""
        if after_seq is not None:
            after = " AND m.seq>?"
            params.append(after_seq)
        params.append(limit)
        with self.db.transaction() as conn:
            rows = conn.execute(
                f"""SELECT m.* FROM messages m JOIN conversations c ON c.id=m.conversation_id
                WHERE m.conversation_id=?{ownership}{after}
                ORDER BY m.seq LIMIT ?""",
                params,
            ).fetchall()
        return [_decode(row) for row in rows]

    def create_asset(
        self, *, client_id: str, source_type: str, media_type: str,
        status: str = "ready", filename: str | None = None,
        mime_type: str | None = None, storage_uri: str | None = None,
        source_url: str | None = None, byte_size: int | None = None,
        sha256: str | None = None, metadata: dict[str, Any] | None = None,
        asset_id: str | None = None, now: datetime | None = None,
    ) -> dict[str, Any]:
        asset_id = asset_id or uuid4().hex
        timestamp = _now(now)
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT INTO assets(
                id,client_id,source_type,media_type,filename,mime_type,storage_uri,
                source_url,byte_size,sha256,status,metadata_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (asset_id, client_id, source_type, media_type, filename, mime_type,
                 storage_uri, source_url, byte_size, sha256, status,
                 json.dumps(metadata or {}, ensure_ascii=False), timestamp, timestamp),
            )
            row = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        return _decode(row)

    def get_asset(self, asset_id: str, *, client_id: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM assets WHERE id=? AND deleted_at IS NULL"
        params: list[Any] = [asset_id]
        if client_id is not None:
            sql += " AND client_id=?"
            params.append(client_id)
        with self.db.transaction() as conn:
            row = conn.execute(sql, params).fetchone()
        return _decode(row) if row else None

    def bind_asset(
        self, message_id: str, asset_id: str, *, usage: str = "input",
        ordinal: int | None = None, caption: str | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        with self.db.transaction(immediate=True) as conn:
            message = conn.execute(
                """SELECT m.id,c.client_id FROM messages m
                JOIN conversations c ON c.id=m.conversation_id WHERE m.id=?""",
                (message_id,),
            ).fetchone()
            asset = conn.execute("SELECT client_id FROM assets WHERE id=? AND deleted_at IS NULL", (asset_id,)).fetchone()
            if message is None or asset is None:
                raise WorkspaceNotFound("message or asset not found")
            if message["client_id"] != asset["client_id"] or (client_id is not None and message["client_id"] != client_id):
                raise WorkspaceConflict("asset and message owners do not match")
            existing = conn.execute(
                "SELECT * FROM message_assets WHERE message_id=? AND asset_id=? AND usage=?",
                (message_id, asset_id, usage),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            if ordinal is None:
                ordinal = int(conn.execute(
                    "SELECT COALESCE(MAX(ordinal),-1)+1 AS ordinal FROM message_assets WHERE message_id=? AND usage=?",
                    (message_id, usage),
                ).fetchone()["ordinal"])
            conn.execute(
                "INSERT INTO message_assets(message_id,asset_id,usage,ordinal,caption) VALUES(?,?,?,?,?)",
                (message_id, asset_id, usage, ordinal, caption),
            )
            row = conn.execute(
                "SELECT * FROM message_assets WHERE message_id=? AND asset_id=? AND usage=?",
                (message_id, asset_id, usage),
            ).fetchone()
        return dict(row)

    def create_task(
        self, *, client_id: str, conversation_id: str, kind: str, title: str,
        request_message_id: str | None = None, params: dict[str, Any] | None = None,
        status: str = "queued", stage: str = "queued", progress: float = 0,
        task_id: str | None = None, now: datetime | None = None,
    ) -> dict[str, Any]:
        task_id = task_id or uuid4().hex
        timestamp = _now(now)
        with self.db.transaction(immediate=True) as conn:
            conversation = conn.execute(
                "SELECT client_id FROM conversations WHERE id=? AND deleted_at IS NULL", (conversation_id,),
            ).fetchone()
            if conversation is None or conversation["client_id"] != client_id:
                raise WorkspaceNotFound("conversation not found")
            if request_message_id is not None:
                message = conn.execute(
                    "SELECT 1 FROM messages WHERE id=? AND conversation_id=?",
                    (request_message_id, conversation_id),
                ).fetchone()
                if message is None:
                    raise WorkspaceConflict("request message is outside the conversation")
            conn.execute(
                """INSERT INTO task_runs(
                id,client_id,conversation_id,request_message_id,kind,title,status,stage,
                progress,params_json,result_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?, ?,?)""",
                (task_id, client_id, conversation_id, request_message_id, kind, title,
                 status, stage, progress, json.dumps(params or {}, ensure_ascii=False),
                 "{}", timestamp, timestamp),
            )
            row = conn.execute("SELECT * FROM task_runs WHERE id=?", (task_id,)).fetchone()
        return _decode(row)

    def get_task(self, task_id: str, *, client_id: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM task_runs WHERE id=? AND deleted_at IS NULL"
        params: list[Any] = [task_id]
        if client_id is not None:
            sql += " AND client_id=?"
            params.append(client_id)
        with self.db.transaction() as conn:
            row = conn.execute(sql, params).fetchone()
        return _decode(row) if row else None

    def update_task(
        self, task_id: str, values: dict[str, Any], *, client_id: str | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        allowed = {
            "result_message_id", "title", "status", "stage", "progress", "params",
            "result", "error_code", "error_message", "finished_at", "deleted_at",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported task fields: {sorted(unknown)}")
        columns: dict[str, Any] = {}
        for key, value in values.items():
            if key == "params":
                columns["params_json"] = json.dumps(value or {}, ensure_ascii=False)
            elif key == "result":
                columns["result_json"] = json.dumps(value or {}, ensure_ascii=False)
            else:
                columns[key] = value
        columns["updated_at"] = _now()
        assignments = ",".join(f"{key}=?" for key in columns)
        where = "id=?"
        params = [*columns.values(), task_id]
        if client_id is not None:
            where += " AND client_id=?"
            params.append(client_id)
        if expected_version is not None:
            where += " AND version=?"
            params.append(expected_version)
        with self.db.transaction(immediate=True) as conn:
            cursor = conn.execute(
                f"UPDATE task_runs SET {assignments},version=version+1 WHERE {where}", params,
            )
            if cursor.rowcount != 1:
                exists = conn.execute("SELECT 1 FROM task_runs WHERE id=?", (task_id,)).fetchone()
                if exists and expected_version is not None:
                    raise WorkspaceConflict("task version changed")
                raise WorkspaceNotFound("task not found")
            row = conn.execute("SELECT * FROM task_runs WHERE id=?", (task_id,)).fetchone()
        return _decode(row)

    def list_tasks(
        self, client_id: str, *, conversation_id: str | None = None,
        statuses: Iterable[str] | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        where = ["client_id=?", "deleted_at IS NULL"]
        params: list[Any] = [client_id]
        if conversation_id is not None:
            where.append("conversation_id=?")
            params.append(conversation_id)
        status_values = list(statuses or [])
        if status_values:
            where.append("status IN (" + ",".join("?" for _ in status_values) + ")")
            params.extend(status_values)
        params.append(limit)
        with self.db.transaction() as conn:
            rows = conn.execute(
                f"SELECT * FROM task_runs WHERE {' AND '.join(where)} ORDER BY updated_at DESC,id LIMIT ?",
                params,
            ).fetchall()
        return [_decode(row) for row in rows]

    def save_storyboard(
        self, task_id: str, shots: list[dict[str, Any]], *, summary: str | None = None,
        status: str = "draft", storyboard_id: str | None = None,
        client_id: str | None = None, now: datetime | None = None,
    ) -> dict[str, Any]:
        if not shots:
            raise ValueError("storyboard requires at least one shot")
        storyboard_id = storyboard_id or uuid4().hex
        timestamp = _now(now)
        with self.db.transaction(immediate=True) as conn:
            task = conn.execute("SELECT client_id FROM task_runs WHERE id=?", (task_id,)).fetchone()
            if task is None or (client_id is not None and task["client_id"] != client_id):
                raise WorkspaceNotFound("task not found")
            version = int(conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 AS version FROM storyboards WHERE task_id=?", (task_id,),
            ).fetchone()["version"])
            conn.execute(
                "INSERT INTO storyboards(id,task_id,version,status,summary,created_at) VALUES(?,?,?,?,?,?)",
                (storyboard_id, task_id, version, status, summary, timestamp),
            )
            seen: set[int] = set()
            for index, shot in enumerate(shots, start=1):
                ordinal = int(shot.get("ordinal", index))
                if ordinal in seen:
                    raise WorkspaceConflict("storyboard shot ordinals must be unique")
                seen.add(ordinal)
                image_asset_id = shot.get("image_asset_id")
                if image_asset_id:
                    asset = conn.execute("SELECT client_id FROM assets WHERE id=?", (image_asset_id,)).fetchone()
                    if asset is None or asset["client_id"] != task["client_id"]:
                        raise WorkspaceConflict("storyboard image asset has a different owner")
                known = {"id", "ordinal", "title", "description", "duration_seconds", "image_asset_id", "status"}
                payload = {key: value for key, value in shot.items() if key not in known}
                conn.execute(
                    """INSERT INTO storyboard_shots(
                    id,storyboard_id,ordinal,title,description,duration_seconds,image_asset_id,status,payload_json
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (shot.get("id") or uuid4().hex, storyboard_id, ordinal, shot.get("title"),
                     shot.get("description"), shot.get("duration_seconds"), image_asset_id,
                     shot.get("status", "draft"), json.dumps(payload, ensure_ascii=False)),
                )
            rows = conn.execute(
                "SELECT * FROM storyboard_shots WHERE storyboard_id=? ORDER BY ordinal", (storyboard_id,),
            ).fetchall()
        return {
            "id": storyboard_id, "task_id": task_id, "version": version, "status": status,
            "summary": summary, "created_at": timestamp, "shots": [_decode(row) for row in rows],
        }

    def list_shots(
        self, task_id: str, *, version: int | None = None,
        client_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [task_id]
        version_clause = ""
        if version is not None:
            version_clause = " AND s.version=?"
            params.append(version)
        ownership = ""
        if client_id is not None:
            ownership = " AND t.client_id=?"
            params.append(client_id)
        with self.db.transaction() as conn:
            storyboard = conn.execute(
                f"""SELECT s.* FROM storyboards s JOIN task_runs t ON t.id=s.task_id
                WHERE s.task_id=?{version_clause}{ownership}
                ORDER BY s.version DESC LIMIT 1""",
                params,
            ).fetchone()
            if storyboard is None:
                return []
            rows = conn.execute(
                "SELECT * FROM storyboard_shots WHERE storyboard_id=? ORDER BY ordinal",
                (storyboard["id"],),
            ).fetchall()
        return [_decode(row) for row in rows]

    @staticmethod
    def _quota_snapshot_conn(
        conn: Any, *, client_id: str, resource: str, client_limit: int,
        global_limit: int, day_cn: str,
    ) -> dict[str, Any]:
        client = conn.execute(
            """SELECT
            COALESCE(SUM(CASE WHEN state='reserved' THEN units ELSE 0 END),0) reserved,
            COALESCE(SUM(CASE WHEN state='committed' THEN units ELSE 0 END),0) committed
            FROM quota_ledger WHERE day_cn=? AND client_id=? AND resource=?""",
            (day_cn, client_id, resource),
        ).fetchone()
        global_row = conn.execute(
            """SELECT
            COALESCE(SUM(CASE WHEN state='reserved' THEN units ELSE 0 END),0) reserved,
            COALESCE(SUM(CASE WHEN state='committed' THEN units ELSE 0 END),0) committed
            FROM quota_ledger WHERE day_cn=? AND resource=?""",
            (day_cn, resource),
        ).fetchone()
        client_used = int(client["reserved"]) + int(client["committed"])
        global_used = int(global_row["reserved"]) + int(global_row["committed"])
        return {
            "day_cn": day_cn, "client_id": client_id, "resource": resource,
            "client_reserved": int(client["reserved"]), "client_committed": int(client["committed"]),
            "client_used": client_used, "client_limit": client_limit,
            "client_remaining": max(0, client_limit - client_used),
            "global_reserved": int(global_row["reserved"]), "global_committed": int(global_row["committed"]),
            "global_used": global_used, "global_limit": global_limit,
            "global_remaining": max(0, global_limit - global_used),
        }

    def quota_snapshot(
        self, *, client_id: str, resource: str, client_limit: int,
        global_limit: int, day_cn: str | None = None,
    ) -> dict[str, Any]:
        day_cn = day_cn or _china_day()
        with self.db.transaction() as conn:
            return self._quota_snapshot_conn(
                conn, client_id=client_id, resource=resource, client_limit=client_limit,
                global_limit=global_limit, day_cn=day_cn,
            )

    def reserve(
        self, *, client_id: str, resource: str, units: int, client_limit: int,
        global_limit: int, task_id: str | None = None, reservation_id: str | None = None,
        day_cn: str | None = None,
    ) -> dict[str, Any]:
        if units <= 0:
            raise ValueError("quota units must be positive")
        if client_limit < 0 or global_limit < 0:
            raise ValueError("quota limits cannot be negative")
        day_cn = day_cn or _china_day()
        reservation_id = reservation_id or uuid4().hex
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            existing = None
            if task_id is not None:
                task = conn.execute("SELECT client_id FROM task_runs WHERE id=?", (task_id,)).fetchone()
                if task is None or task["client_id"] != client_id:
                    raise WorkspaceNotFound("task not found")
                existing = conn.execute(
                    "SELECT * FROM quota_ledger WHERE task_id=? AND resource=?", (task_id, resource),
                ).fetchone()
            if existing is not None:
                if int(existing["units"]) != units or existing["client_id"] != client_id or existing["day_cn"] != day_cn:
                    raise WorkspaceConflict("quota reservation does not match the existing task reservation")
                if existing["state"] in {"reserved", "committed"}:
                    snapshot = self._quota_snapshot_conn(
                        conn, client_id=client_id, resource=resource, client_limit=client_limit,
                        global_limit=global_limit, day_cn=day_cn,
                    )
                    return {"reservation": dict(existing), "snapshot": snapshot}
                reservation_id = existing["id"]
            snapshot = self._quota_snapshot_conn(
                conn, client_id=client_id, resource=resource, client_limit=client_limit,
                global_limit=global_limit, day_cn=day_cn,
            )
            if snapshot["client_used"] + units > client_limit:
                raise QuotaExceeded("client quota exceeded", snapshot)
            if snapshot["global_used"] + units > global_limit:
                raise QuotaExceeded("global quota exceeded", snapshot)
            if existing is None:
                conn.execute(
                    """INSERT INTO quota_ledger(
                    id,day_cn,client_id,resource,units,state,task_id,created_at,updated_at
                    ) VALUES(?,?,?,?,?,'reserved',?,?,?)""",
                    (reservation_id, day_cn, client_id, resource, units, task_id, timestamp, timestamp),
                )
            else:
                conn.execute(
                    """UPDATE quota_ledger SET state='reserved',updated_at=?,committed_at=NULL,released_at=NULL
                    WHERE id=?""",
                    (timestamp, reservation_id),
                )
            row = conn.execute("SELECT * FROM quota_ledger WHERE id=?", (reservation_id,)).fetchone()
            snapshot = self._quota_snapshot_conn(
                conn, client_id=client_id, resource=resource, client_limit=client_limit,
                global_limit=global_limit, day_cn=day_cn,
            )
        return {"reservation": dict(row), "snapshot": snapshot}

    def _transition_quota(
        self, target: str, *, reservation_id: str | None, task_id: str | None,
        resource: str | None, client_id: str | None,
    ) -> dict[str, Any]:
        if reservation_id is None and (task_id is None or resource is None):
            raise ValueError("reservation_id or task_id plus resource is required")
        with self.db.transaction(immediate=True) as conn:
            if reservation_id is not None:
                row = conn.execute("SELECT * FROM quota_ledger WHERE id=?", (reservation_id,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM quota_ledger WHERE task_id=? AND resource=?", (task_id, resource),
                ).fetchone()
            if row is None or (client_id is not None and row["client_id"] != client_id):
                raise WorkspaceNotFound("quota reservation not found")
            if row["state"] == target:
                return dict(row)
            if row["state"] != "reserved":
                raise WorkspaceConflict(f"cannot transition quota from {row['state']} to {target}")
            timestamp = _now()
            time_column = "committed_at" if target == "committed" else "released_at"
            conn.execute(
                f"UPDATE quota_ledger SET state=?,updated_at=?,{time_column}=? WHERE id=?",
                (target, timestamp, timestamp, row["id"]),
            )
            updated = conn.execute("SELECT * FROM quota_ledger WHERE id=?", (row["id"],)).fetchone()
        return dict(updated)

    def commit(
        self, reservation_id: str | None = None, *, task_id: str | None = None,
        resource: str | None = None, client_id: str | None = None,
    ) -> dict[str, Any]:
        return self._transition_quota(
            "committed", reservation_id=reservation_id, task_id=task_id,
            resource=resource, client_id=client_id,
        )

    def release(
        self, reservation_id: str | None = None, *, task_id: str | None = None,
        resource: str | None = None, client_id: str | None = None,
    ) -> dict[str, Any]:
        return self._transition_quota(
            "released", reservation_id=reservation_id, task_id=task_id,
            resource=resource, client_id=client_id,
        )

    def backfill_legacy(self) -> dict[str, int]:
        """Project legacy jobs into v2 tables without changing the source rows."""
        counters = {"conversations": 0, "tasks": 0, "messages": 0, "assets": 0, "training_examples": 0}
        with self.db.transaction(immediate=True) as conn:
            jobs = conn.execute(
                """SELECT j.* FROM jobs j
                LEFT JOIN task_jobs tj ON tj.job_id=j.id
                WHERE tj.job_id IS NULL
                ORDER BY j.client_id,j.queued_at,j.id"""
            ).fetchall()
            for source in jobs:
                job = dict(source)
                client_id = job["client_id"]
                conversation_id = _stable_id("legacy-conversation", client_id)
                created_at = job["queued_at"]
                updated_at = job.get("finished_at") or job.get("started_at") or created_at
                inserted = conn.execute(
                    """INSERT OR IGNORE INTO conversations(
                    id,client_id,title,status,created_at,updated_at
                    ) VALUES(?,?,?,'active',?,?)""",
                    (conversation_id, client_id, "历史生成", created_at, updated_at),
                )
                counters["conversations"] += int(inserted.rowcount == 1)
                conn.execute(
                    """UPDATE conversations SET updated_at=CASE WHEN updated_at<? THEN ? ELSE updated_at END
                    WHERE id=?""",
                    (updated_at, updated_at, conversation_id),
                )
                next_seq = int(conn.execute(
                    "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM messages WHERE conversation_id=?",
                    (conversation_id,),
                ).fetchone()["seq"])
                user_message_id = _stable_id("legacy-user-message", job["id"])
                assistant_message_id = _stable_id("legacy-assistant-message", job["id"])
                conn.execute(
                    """INSERT OR IGNORE INTO messages(
                    id,conversation_id,seq,role,kind,content_text,content_json,status,created_at,updated_at
                    ) VALUES(?,?,?,'user','text',?,?,'complete',?,?)""",
                    (user_message_id, conversation_id, next_seq, job["prompt_user"],
                     json.dumps({"legacy_job_id": job["id"], "prompt_final": job["prompt_final"]}, ensure_ascii=False),
                     created_at, created_at),
                )
                terminal = job["status"] in {"succeeded", "failed"}
                assistant_text = "历史生成结果" if job["status"] == "succeeded" else (
                    job.get("error_message") or "历史生成任务已迁移"
                )
                assistant_kind = "media" if job["status"] == "succeeded" else (
                    "error" if job["status"] == "failed" else "status"
                )
                assistant_status = "complete" if terminal else "pending"
                conn.execute(
                    """INSERT OR IGNORE INTO messages(
                    id,conversation_id,seq,role,kind,content_text,content_json,status,
                    reply_to_message_id,created_at,updated_at
                    ) VALUES(?,?,?,'assistant',?,?,?,?,?,?,?)""",
                    (assistant_message_id, conversation_id, next_seq + 1, assistant_kind,
                     assistant_text, json.dumps({"legacy_job_id": job["id"]}, ensure_ascii=False),
                     assistant_status, user_message_id, updated_at, updated_at),
                )
                counters["messages"] += 2
                task_id = _stable_id("legacy-task", job["id"])
                progress = 1.0 if terminal else (0.5 if job["status"] == "running" else 0.0)
                stage = "completed" if job["status"] == "succeeded" else (
                    "failed" if job["status"] == "failed" else job["status"]
                )
                result = {
                    "result_url": job.get("result_url"),
                    "result_meta": _loads(job.get("result_meta_json"), {}),
                    "legacy_job_id": job["id"],
                }
                conn.execute(
                    """INSERT OR IGNORE INTO task_runs(
                    id,client_id,conversation_id,request_message_id,result_message_id,kind,title,
                    status,stage,progress,params_json,result_json,error_code,error_message,
                    created_at,updated_at,finished_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task_id, client_id, conversation_id, user_message_id, assistant_message_id,
                     "generate", "历史图片生成" if job["mode"] == "image" else "历史视频生成",
                     job["status"], stage, progress, job["params_json"],
                     json.dumps(result, ensure_ascii=False), job.get("error_code"), job.get("error_message"),
                     created_at, updated_at, job.get("finished_at")),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO task_jobs(task_id,job_id,role,ordinal) VALUES(?,?,'primary',0)",
                    (task_id, job["id"]),
                )
                counters["tasks"] += 1
                if job.get("result_url"):
                    asset_id = _stable_id("legacy-result-asset", job["id"])
                    asset_insert = conn.execute(
                        """INSERT OR IGNORE INTO assets(
                        id,client_id,source_type,media_type,storage_uri,status,metadata_json,created_at,updated_at
                        ) VALUES(?,?, 'generated',?,?,'ready',?,?,?)""",
                        (asset_id, client_id, job["mode"], job["result_url"],
                         json.dumps({"legacy_job_id": job["id"]}, ensure_ascii=False), updated_at, updated_at),
                    )
                    counters["assets"] += int(asset_insert.rowcount == 1)
                    conn.execute(
                        """INSERT OR IGNORE INTO message_assets(message_id,asset_id,usage,ordinal,caption)
                        VALUES(?,?,'result',0,'历史生成结果')""",
                        (assistant_message_id, asset_id),
                    )
                if terminal:
                    example_id = _stable_id("legacy-training-example", job["id"])
                    example_insert = conn.execute(
                        """INSERT OR IGNORE INTO training_examples(
                        id,client_id,conversation_id,input_message_id,output_message_id,task_id,
                        schema_version,input_json,output_json,labels_json,quality_json,eligibility,
                        created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,2,?,?,?,?,'eligible',?,?)""",
                        (example_id, client_id, conversation_id, user_message_id, assistant_message_id,
                         task_id, json.dumps({"text": job["prompt_user"]}, ensure_ascii=False),
                         json.dumps(result, ensure_ascii=False),
                         json.dumps({"mode": job["mode"], "legacy": True}, ensure_ascii=False),
                         json.dumps({"status": job["status"]}, ensure_ascii=False), updated_at, updated_at),
                    )
                    counters["training_examples"] += int(example_insert.rowcount == 1)
                if job["mode"] == "video" and job["status"] in {"queued", "running", "succeeded"}:
                    params = _loads(job["params_json"], {})
                    day_cn = params.get("reservation_day") or _china_day(created_at)
                    state = "committed" if job["status"] == "succeeded" else "reserved"
                    quota_id = _stable_id("legacy-video-quota", job["id"])
                    conn.execute(
                        """INSERT OR IGNORE INTO quota_ledger(
                        id,day_cn,client_id,resource,units,state,task_id,created_at,updated_at,committed_at
                        ) VALUES(?,?,?,'video',1,?,?,?,?,?)""",
                        (quota_id, day_cn, client_id, state, task_id, created_at, updated_at,
                         updated_at if state == "committed" else None),
                    )
                conn.execute(
                    """INSERT OR IGNORE INTO activity_events(
                    ts,client_id,event_type,conversation_id,task_id,dedupe_key,payload_json
                    ) VALUES(?,?,'legacy_backfill',?,?,?,?)""",
                    (updated_at, client_id, conversation_id, task_id,
                     f"legacy_backfill:{job['id']}", json.dumps({"job_id": job["id"]}, ensure_ascii=False)),
                )
        return counters

    def backfill_legacy_jobs(self) -> dict[str, int]:
        return self.backfill_legacy()
