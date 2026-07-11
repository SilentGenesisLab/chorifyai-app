from __future__ import annotations

import hashlib
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
    "annotation_json": "annotation",
    "evidence_json": "evidence",
    "private_trace_json": "private_trace",
    "envelope_json": "envelope",
    "must_preserve_json": "must_preserve",
    "provider_requirements_json": "provider_requirements",
    "fallback_plan_json": "fallback_plan",
    "capability_snapshot_json": "capability_snapshot",
    "qc_json": "qc",
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


def _snapshot_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _required_storyboard_panels(shot: dict[str, Any], index: int) -> list[dict[str, Any]]:
    label = f"storyboard shot {shot.get('ordinal') or index}"
    raw_panels = shot.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        raise ValueError(f"{label} requires at least one confirmation panel")
    if not all(isinstance(panel, dict) for panel in raw_panels):
        raise ValueError(f"{label} panels must be objects")
    required = [panel for panel in raw_panels if panel.get("required", True)]
    if not required:
        raise ValueError(f"{label} requires at least one required panel")
    ordinals: set[int] = set()
    logical_keys: set[str] = set()
    for panel_index, panel in enumerate(raw_panels, start=1):
        ordinal = int(panel.get("ordinal") or panel_index)
        logical_key = str(panel.get("logical_key") or panel.get("role") or f"panel-{ordinal}")
        if ordinal in ordinals or logical_key in logical_keys:
            raise ValueError(f"{label} panel ordinals and logical keys must be unique")
        ordinals.add(ordinal)
        logical_keys.add(logical_key)
        if panel not in required:
            continue
        if not str(panel.get("description") or "").strip():
            raise ValueError(f"{label} required panels need descriptions")
        if not panel.get("clean_asset_id") or not panel.get("selected_asset_id"):
            raise ValueError(f"{label} required panels need selected clean frames")
        if not panel.get("send_to_provider"):
            raise ValueError(f"{label} required clean frames must be sendable")
        if panel.get("annotated_asset_id") == panel.get("selected_asset_id"):
            raise ValueError(f"{label} annotated panels cannot be selected clean frames")
    return raw_panels


def _insert_workflow_event(
    conn: Any, *, task_id: str, client_id: str, event_type: str,
    payload: dict[str, Any] | None = None, created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or _now()
    cursor = conn.execute(
        "INSERT INTO workflow_events(task_id,client_id,event_type,envelope_json,created_at) VALUES(?,?,?,?,?)",
        (task_id, client_id, event_type, "{}", timestamp),
    )
    event_id = int(cursor.lastrowid)
    data = payload or {}
    envelope = {
        "schema": "hook.event.v1", "id": event_id, "task_id": task_id,
        "type": event_type, "ts": timestamp, "data": data,
    }
    public_label = data.get("public_label") or data.get("label")
    message = data.get("message")
    state = data.get("state") or data.get("status")
    queue = data.get("counts") if isinstance(data.get("counts"), dict) else data.get("queue")
    snapshot = data.get("snapshot") or data.get("counts")
    for key, value in (
        ("public_label", public_label), ("message", message), ("state", state),
        ("input_count", data.get("input_count")), ("output_count", data.get("output_count")),
        ("heartbeat_at", data.get("last_heartbeat")), ("queue", queue), ("snapshot", snapshot),
    ):
        if value not in (None, ""):
            envelope[key] = value
    conn.execute(
        "UPDATE workflow_events SET envelope_json=? WHERE id=?",
        (json.dumps(envelope, ensure_ascii=False, separators=(",", ":")), event_id),
    )
    return {"id": event_id, "task_id": task_id, "client_id": client_id,
            "event_type": event_type, "envelope": envelope, "created_at": timestamp}


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

    def get_asset_by_storage_uri(
        self, storage_uri: str, *, client_id: str,
    ) -> dict[str, Any] | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                """SELECT * FROM assets WHERE storage_uri=? AND client_id=?
                AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1""",
                (storage_uri, client_id),
            ).fetchone()
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
            _insert_workflow_event(
                conn, task_id=task_id, client_id=client_id, event_type="task.created",
                payload={"status": status, "stage": stage, "progress": progress, "version": 1},
                created_at=timestamp,
            )
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

    def create_image_edit_contract(
        self, *, client_id: str, conversation_id: str, task_id: str,
        base_asset_id: str, prompt_user: str, prompt_final: str,
        router_version: str, domain: str, fidelity_label: str,
        mask_asset_id: str | None = None, annotation_asset_id: str | None = None,
        must_preserve: list[str] | None = None,
        provider_requirements: list[str] | None = None,
        fallback_plan: list[str] | None = None,
        capability_snapshot: dict[str, Any] | None = None,
        contract_id: str | None = None,
    ) -> dict[str, Any]:
        contract_id = contract_id or uuid4().hex
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            task = conn.execute(
                "SELECT client_id,conversation_id FROM task_runs WHERE id=?", (task_id,),
            ).fetchone()
            asset_ids = [base_asset_id, mask_asset_id, annotation_asset_id]
            owned = conn.execute(
                "SELECT COUNT(*) AS count FROM assets WHERE id IN (?,?,?) AND client_id=? AND deleted_at IS NULL",
                (*asset_ids, client_id),
            ).fetchone()["count"]
            expected_owned = len({item for item in asset_ids if item})
            if task is None or task["client_id"] != client_id or task["conversation_id"] != conversation_id:
                raise WorkspaceNotFound("task not found")
            if int(owned) != expected_owned:
                raise WorkspaceConflict("image edit assets must belong to the current client")
            conn.execute(
                """INSERT INTO image_edit_contracts(
                id,client_id,conversation_id,task_id,router_version,domain,fidelity_label,
                base_asset_id,mask_asset_id,annotation_asset_id,prompt_user,prompt_final,
                must_preserve_json,provider_requirements_json,fallback_plan_json,
                capability_snapshot_json,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    contract_id, client_id, conversation_id, task_id, router_version, domain,
                    fidelity_label, base_asset_id, mask_asset_id, annotation_asset_id,
                    prompt_user, prompt_final, json.dumps(must_preserve or [], ensure_ascii=False),
                    json.dumps(provider_requirements or [], ensure_ascii=False),
                    json.dumps(fallback_plan or [], ensure_ascii=False),
                    json.dumps(capability_snapshot or {}, ensure_ascii=False), "queued", timestamp, timestamp,
                ),
            )
            row = conn.execute("SELECT * FROM image_edit_contracts WHERE id=?", (contract_id,)).fetchone()
        return _decode(row)

    def get_image_edit_contract(self, task_id: str, *, client_id: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM image_edit_contracts WHERE task_id=?"
        params: list[Any] = [task_id]
        if client_id is not None:
            sql += " AND client_id=?"
            params.append(client_id)
        with self.db.transaction() as conn:
            row = conn.execute(sql, params).fetchone()
        return _decode(row) if row else None

    def update_image_edit_contract(self, task_id: str, *, status: str, capability_snapshot: dict[str, Any] | None = None) -> None:
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            if capability_snapshot is None:
                cursor = conn.execute(
                    "UPDATE image_edit_contracts SET status=?,updated_at=? WHERE task_id=?",
                    (status, timestamp, task_id),
                )
            else:
                cursor = conn.execute(
                    """UPDATE image_edit_contracts SET status=?,capability_snapshot_json=?,updated_at=?
                    WHERE task_id=?""",
                    (status, json.dumps(capability_snapshot, ensure_ascii=False), timestamp, task_id),
                )
            if cursor.rowcount != 1:
                raise WorkspaceNotFound("image edit contract not found")

    def record_asset_version(
        self, *, client_id: str, asset_id: str, parent_asset_id: str | None,
        edit_contract_id: str | None, relation: str, qc: dict[str, Any] | None = None,
        selected: bool = False,
    ) -> dict[str, Any]:
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            asset = conn.execute(
                "SELECT client_id FROM assets WHERE id=? AND deleted_at IS NULL", (asset_id,),
            ).fetchone()
            parent = conn.execute(
                "SELECT client_id FROM assets WHERE id=? AND deleted_at IS NULL", (parent_asset_id,),
            ).fetchone() if parent_asset_id else None
            if asset is None or asset["client_id"] != client_id or (parent and parent["client_id"] != client_id):
                raise WorkspaceConflict("asset version owners do not match")
            version = int(conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 AS version FROM asset_versions WHERE client_id=? AND parent_asset_id IS ?",
                (client_id, parent_asset_id),
            ).fetchone()["version"])
            version_id = uuid4().hex
            conn.execute(
                """INSERT INTO asset_versions(
                id,client_id,asset_id,parent_asset_id,edit_contract_id,version,relation,selected,qc_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (version_id, client_id, asset_id, parent_asset_id, edit_contract_id, version,
                 relation, int(selected), json.dumps(qc or {}, ensure_ascii=False), timestamp),
            )
            row = conn.execute("SELECT * FROM asset_versions WHERE id=?", (version_id,)).fetchone()
        return _decode(row)

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
            _insert_workflow_event(
                conn, task_id=task_id, client_id=row["client_id"], event_type="task.updated",
                payload={
                    "status": row["status"], "stage": row["stage"],
                    "progress": row["progress"], "version": row["version"],
                    "indeterminate": row["status"] in {"planning", "generating", "assembling"},
                },
            )
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
        for index, shot in enumerate(shots, start=1):
            if not isinstance(shot, dict):
                raise ValueError("storyboard shots must be objects")
            _required_storyboard_panels(shot, index)
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
                """INSERT INTO storyboards(
                id,task_id,version,status,summary,created_at,updated_at,revision
                ) VALUES(?,?,?,?,?,?,?,1)""",
                (storyboard_id, task_id, version, status, summary, timestamp, timestamp),
            )
            seen: set[int] = set()
            for index, shot in enumerate(shots, start=1):
                ordinal = int(shot.get("ordinal", index))
                if ordinal in seen:
                    raise WorkspaceConflict("storyboard shot ordinals must be unique")
                seen.add(ordinal)
                panel_values = _required_storyboard_panels(shot, index)
                image_asset_id = shot.get("image_asset_id") or next(
                    (panel.get("selected_asset_id") or panel.get("clean_asset_id") for panel in panel_values
                     if panel.get("selected_asset_id") or panel.get("clean_asset_id")), None,
                )
                if image_asset_id:
                    asset = conn.execute("SELECT client_id FROM assets WHERE id=?", (image_asset_id,)).fetchone()
                    if asset is None or asset["client_id"] != task["client_id"]:
                        raise WorkspaceConflict("storyboard image asset has a different owner")
                known = {"id", "ordinal", "title", "description", "duration_seconds", "image_asset_id", "status", "panels"}
                payload = {key: value for key, value in shot.items() if key not in known}
                shot_id = shot.get("id") or uuid4().hex
                conn.execute(
                    """INSERT INTO storyboard_shots(
                    id,storyboard_id,ordinal,title,description,duration_seconds,image_asset_id,status,payload_json
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (shot_id, storyboard_id, ordinal, shot.get("title"),
                     shot.get("description"), shot.get("duration_seconds"), image_asset_id,
                     shot.get("status", "draft"), json.dumps(payload, ensure_ascii=False)),
                )
                for panel_index, panel in enumerate(panel_values, start=1):
                    panel_ordinal = int(panel.get("ordinal") or panel_index)
                    logical_key = str(panel.get("logical_key") or panel.get("role") or f"panel-{panel_ordinal}")
                    clean_asset_id = panel.get("clean_asset_id")
                    selected_asset_id = panel.get("selected_asset_id") or clean_asset_id
                    annotated_asset_id = panel.get("annotated_asset_id")
                    for candidate_id in (clean_asset_id, selected_asset_id, annotated_asset_id):
                        if not candidate_id:
                            continue
                        candidate = conn.execute(
                            """SELECT client_id,source_type,media_type,status,storage_uri,deleted_at
                            FROM assets WHERE id=?""", (candidate_id,),
                        ).fetchone()
                        if candidate is None or candidate["client_id"] != task["client_id"]:
                            raise WorkspaceConflict("storyboard panel asset has a different owner")
                        if candidate["deleted_at"] is not None:
                            raise WorkspaceConflict("storyboard panel asset has been deleted")
                        if candidate_id in {clean_asset_id, selected_asset_id} and (
                            candidate["source_type"] != "storyboard_clean"
                            or candidate["media_type"] != "image"
                            or candidate["status"] != "ready"
                            or not candidate["storage_uri"]
                        ):
                            raise WorkspaceConflict("storyboard clean frame is not ready")
                    conn.execute(
                        """INSERT INTO storyboard_panels(
                        id,storyboard_id,shot_id,logical_key,ordinal,revision,role,required,
                        description,annotation_json,annotated_asset_id,clean_asset_id,selected_asset_id,
                        send_to_provider,status,metadata_json,created_at,updated_at
                        ) VALUES(?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (panel.get("id") or uuid4().hex, storyboard_id, shot_id, logical_key, panel_ordinal,
                         str(panel.get("role") or logical_key), 1 if panel.get("required", True) else 0,
                         str(panel.get("description") or ""), json.dumps(panel.get("annotation") or {}, ensure_ascii=False),
                         annotated_asset_id, clean_asset_id, selected_asset_id,
                         1 if panel.get("send_to_provider") else 0, str(panel.get("status") or "draft"),
                         json.dumps(panel.get("metadata") or {}, ensure_ascii=False), timestamp, timestamp),
                    )
            rows = conn.execute(
                "SELECT * FROM storyboard_shots WHERE storyboard_id=? ORDER BY ordinal", (storyboard_id,),
            ).fetchall()
        return {
            "id": storyboard_id, "task_id": task_id, "version": version, "status": status,
            "revision": 1, "summary": summary, "created_at": timestamp, "updated_at": timestamp,
            "animatic_status": "missing", "shots": [_decode(row) for row in rows],
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

    def get_storyboard(self, storyboard_id: str, *, client_id: str) -> dict[str, Any] | None:
        with self.db.transaction() as conn:
            board_row = conn.execute(
                """SELECT s.*,t.client_id FROM storyboards s JOIN task_runs t ON t.id=s.task_id
                WHERE s.id=? AND t.client_id=? AND t.deleted_at IS NULL""",
                (storyboard_id, client_id),
            ).fetchone()
            if board_row is None:
                return None
            shot_rows = conn.execute(
                "SELECT * FROM storyboard_shots WHERE storyboard_id=? ORDER BY ordinal,id", (storyboard_id,),
            ).fetchall()
            panel_rows = conn.execute(
                """SELECT p.* FROM storyboard_panels p
                WHERE p.storyboard_id=? AND p.superseded_at IS NULL
                AND NOT EXISTS (
                  SELECT 1 FROM storyboard_panels newer
                  WHERE newer.shot_id=p.shot_id AND newer.logical_key=p.logical_key
                  AND newer.revision>p.revision AND newer.superseded_at IS NULL
                ) ORDER BY p.shot_id,p.ordinal,p.id""",
                (storyboard_id,),
            ).fetchall()
            decision_rows = conn.execute(
                """SELECT * FROM approval_decisions WHERE storyboard_id=?
                ORDER BY created_at,id""", (storyboard_id,),
            ).fetchall()
            skill_rows = conn.execute(
                """SELECT id,task_id,storyboard_id,shot_id,skill_id,skill_version,stage,status,
                blocking,public_label,input_count,output_count,duration_ms,retry_count,blocking_reason,
                evidence_json,created_at,finished_at FROM skill_runs
                WHERE task_id=? ORDER BY created_at,id""", (board_row["task_id"],),
            ).fetchall()
        board = _decode(board_row)
        decisions = [_decode(row) for row in decision_rows]
        latest = {(item["scope"], item["target_id"]): item for item in decisions}
        panels_by_shot: dict[str, list[dict[str, Any]]] = {}
        for row in panel_rows:
            panel = _decode(row)
            panel["required"] = bool(panel.get("required"))
            panel["send_to_provider"] = bool(panel.get("send_to_provider"))
            decision = latest.get(("panel", panel["id"]))
            panel["approved"] = bool(
                decision and decision.get("decision") == "approved"
                and int(decision.get("target_revision") or 0) == int(panel.get("revision") or 1)
            )
            panels_by_shot.setdefault(panel["shot_id"], []).append(panel)
        shots: list[dict[str, Any]] = []
        for row in shot_rows:
            shot = _decode(row)
            shot["panels"] = panels_by_shot.get(shot["id"], [])
            decision = latest.get(("shot", shot["id"]))
            shot["approved"] = bool(
                decision and decision.get("decision") == "approved"
                and int(decision.get("target_revision") or 0) == int(shot.get("revision") or 1)
            )
            shots.append(shot)
        board_decision = latest.get(("board", storyboard_id))
        board["board_approved"] = bool(
            board_decision and board_decision.get("decision") == "approved"
            and int(board_decision.get("target_revision") or 0) == int(board.get("revision") or 1)
        )
        board["shots"] = shots
        board["approvals"] = decisions
        board["skill_runs"] = [_decode(row) for row in skill_rows]
        board["coverage"] = {
            "shots_total": len(shots),
            "shots_approved": sum(1 for shot in shots if shot["approved"]),
            "panels_total": sum(len(shot["panels"]) for shot in shots),
            "panels_approved": sum(1 for shot in shots for panel in shot["panels"] if panel["approved"]),
            "clean_frames": sum(1 for shot in shots if any(panel.get("selected_asset_id") for panel in shot["panels"])),
        }
        return board

    def list_approvals(self, storyboard_id: str, *, client_id: str) -> list[dict[str, Any]]:
        if self.get_storyboard(storyboard_id, client_id=client_id) is None:
            return []
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_decisions WHERE storyboard_id=? AND client_id=? ORDER BY created_at,id",
                (storyboard_id, client_id),
            ).fetchall()
        return [_decode(row) for row in rows]

    def append_workflow_event(
        self, task_id: str, *, client_id: str, event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.db.transaction(immediate=True) as conn:
            task = conn.execute(
                "SELECT id FROM task_runs WHERE id=? AND client_id=? AND deleted_at IS NULL", (task_id, client_id),
            ).fetchone()
            if task is None:
                raise WorkspaceNotFound("task not found")
            return _insert_workflow_event(
                conn, task_id=task_id, client_id=client_id, event_type=event_type, payload=payload,
            )

    def list_workflow_events(
        self, task_id: str, *, client_id: str, after_id: int = 0, limit: int = 200,
    ) -> list[dict[str, Any]]:
        if self.get_task(task_id, client_id=client_id) is None:
            raise WorkspaceNotFound("task not found")
        with self.db.transaction() as conn:
            rows = conn.execute(
                """SELECT * FROM workflow_events WHERE task_id=? AND client_id=? AND id>?
                ORDER BY id LIMIT ?""", (task_id, client_id, max(0, after_id), min(max(1, limit), 500)),
            ).fetchall()
        return [_decode(row) for row in rows]

    def get_idempotent_submission(
        self, *, client_id: str, conversation_id: str, idempotency_key: str,
    ) -> dict[str, Any] | None:
        dedupe_key = f"message.submit:{client_id}:{idempotency_key}"
        with self.db.transaction() as conn:
            row = conn.execute(
                """SELECT payload_json FROM activity_events
                WHERE client_id=? AND conversation_id=? AND dedupe_key=?""",
                (client_id, conversation_id, dedupe_key),
            ).fetchone()
            if row is None:
                return None
            payload = _loads(row["payload_json"], {})
            message_row = conn.execute(
                """SELECT m.* FROM messages m JOIN conversations c ON c.id=m.conversation_id
                WHERE m.id=? AND c.client_id=? AND c.id=?""",
                (str(payload.get("message_id") or ""), client_id, conversation_id),
            ).fetchone()
        message = _decode(message_row) if message_row is not None else None
        task = self.get_task(str(payload.get("task_id") or ""), client_id=client_id)
        if message is None or task is None:
            return None
        return {"message": message, "task": task}

    def record_idempotent_submission(
        self, *, client_id: str, conversation_id: str, idempotency_key: str,
        message_id: str, task_id: str,
    ) -> dict[str, Any]:
        dedupe_key = f"message.submit:{client_id}:{idempotency_key}"
        timestamp = _now()
        payload = {"message_id": message_id, "task_id": task_id}
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO activity_events(
                ts,client_id,event_type,conversation_id,message_id,task_id,dedupe_key,payload_json
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (timestamp, client_id, "message.submitted", conversation_id, message_id, task_id,
                 dedupe_key, json.dumps(payload, ensure_ascii=False)),
            )
            row = conn.execute(
                "SELECT payload_json FROM activity_events WHERE dedupe_key=?", (dedupe_key,),
            ).fetchone()
        return _loads(row["payload_json"], payload) if row is not None else payload

    def record_skill_run(
        self, *, task_id: str, skill_id: str, skill_version: str, stage: str,
        status: str, blocking: bool, public_label: str, input_hash: str, output_hash: str,
        input_count: int, output_count: int, duration_ms: int, retry_count: int,
        blocking_reason: str | None, evidence: dict[str, Any], private_trace: dict[str, Any],
        storyboard_id: str | None = None, shot_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = uuid4().hex
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            task = conn.execute("SELECT client_id FROM task_runs WHERE id=?", (task_id,)).fetchone()
            if task is None:
                raise WorkspaceNotFound("task not found")
            conn.execute(
                """INSERT INTO skill_runs(
                id,task_id,storyboard_id,shot_id,skill_id,skill_version,stage,status,blocking,
                public_label,input_hash,output_hash,input_count,output_count,duration_ms,retry_count,
                blocking_reason,evidence_json,private_trace_json,created_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, task_id, storyboard_id, shot_id, skill_id, skill_version, stage, status,
                 1 if blocking else 0, public_label, input_hash, output_hash, input_count, output_count,
                 duration_ms, retry_count, blocking_reason, json.dumps(evidence, ensure_ascii=False),
                 json.dumps(private_trace, ensure_ascii=False), timestamp, timestamp),
            )
            _insert_workflow_event(
                conn, task_id=task_id, client_id=task["client_id"], event_type="skill.completed",
                payload={"skill_id": skill_id, "version": skill_version, "stage": stage,
                         "status": status, "label": public_label, "duration_ms": duration_ms,
                         "input_count": input_count, "output_count": output_count,
                         "blocking_reason": blocking_reason},
            )
            row = conn.execute("SELECT * FROM skill_runs WHERE id=?", (run_id,)).fetchone()
        return _decode(row)

    def patch_storyboard_shot(
        self, storyboard_id: str, shot_id: str, *, client_id: str,
        expected_version: int, values: dict[str, Any],
    ) -> dict[str, Any]:
        allowed_columns = {"title", "description", "duration_seconds"}
        allowed_payload = {
            "story_function", "visual", "shot_size", "camera_angle", "camera_height", "lens_feel",
            "composition", "action_start", "action_trigger", "action_result", "camera_move", "sound",
            "transition", "stable_truth", "may_vary", "reference_manifest", "first_failure_cue",
        }
        if set(values) - allowed_columns - allowed_payload:
            raise ValueError("unsupported storyboard shot fields")
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            board = conn.execute(
                """SELECT s.*,t.client_id FROM storyboards s JOIN task_runs t ON t.id=s.task_id
                WHERE s.id=? AND t.client_id=?""", (storyboard_id, client_id),
            ).fetchone()
            if board is None:
                raise WorkspaceNotFound("storyboard not found")
            if int(board["revision"]) != expected_version:
                raise WorkspaceConflict("storyboard version changed")
            if board["frozen_snapshot_hash"]:
                raise WorkspaceConflict("approved storyboard is frozen")
            shot = conn.execute(
                "SELECT * FROM storyboard_shots WHERE id=? AND storyboard_id=?", (shot_id, storyboard_id),
            ).fetchone()
            if shot is None:
                raise WorkspaceNotFound("shot not found")
            payload = _loads(shot["payload_json"], {})
            for key in allowed_payload:
                if key in values:
                    payload[key] = values[key]
            columns = {key: values[key] for key in allowed_columns if key in values}
            columns["payload_json"] = json.dumps(payload, ensure_ascii=False)
            assignments = ",".join(f"{key}=?" for key in columns)
            conn.execute(
                f"UPDATE storyboard_shots SET {assignments},revision=revision+1 WHERE id=?",
                (*columns.values(), shot_id),
            )
            conn.execute(
                """UPDATE storyboards SET revision=revision+1,updated_at=?,animatic_status='stale',
                animatic_confirmed_at=NULL,frozen_snapshot_hash=NULL WHERE id=?""", (timestamp, storyboard_id),
            )
            updated = conn.execute("SELECT revision FROM storyboards WHERE id=?", (storyboard_id,)).fetchone()
            _insert_workflow_event(
                conn, task_id=board["task_id"], client_id=client_id, event_type="shot.revised",
                payload={"storyboard_id": storyboard_id, "shot_id": shot_id, "version": updated["revision"]},
            )
        result = self.get_storyboard(storyboard_id, client_id=client_id)
        assert result is not None
        return result

    def revise_panel(
        self, panel_id: str, *, client_id: str, expected_version: int,
        clean_asset_id: str, description: str | None = None,
    ) -> dict[str, Any]:
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            panel = conn.execute(
                """SELECT p.*,s.task_id,s.revision board_revision,s.frozen_snapshot_hash,t.client_id
                FROM storyboard_panels p JOIN storyboards s ON s.id=p.storyboard_id
                JOIN task_runs t ON t.id=s.task_id WHERE p.id=? AND t.client_id=?""",
                (panel_id, client_id),
            ).fetchone()
            if panel is None:
                raise WorkspaceNotFound("panel not found")
            if int(panel["board_revision"]) != expected_version:
                raise WorkspaceConflict("storyboard version changed")
            if panel["frozen_snapshot_hash"]:
                raise WorkspaceConflict("approved storyboard is frozen")
            asset = conn.execute("SELECT client_id FROM assets WHERE id=?", (clean_asset_id,)).fetchone()
            if asset is None or asset["client_id"] != client_id:
                raise WorkspaceConflict("panel asset has a different owner")
            next_revision = int(panel["revision"]) + 1
            new_id = uuid4().hex
            conn.execute("UPDATE storyboard_panels SET superseded_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, panel_id))
            conn.execute(
                """INSERT INTO storyboard_panels(
                id,storyboard_id,shot_id,logical_key,ordinal,revision,role,required,description,
                annotation_json,annotated_asset_id,clean_asset_id,selected_asset_id,send_to_provider,
                status,metadata_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,'draft',?,?,?)""",
                (new_id, panel["storyboard_id"], panel["shot_id"], panel["logical_key"], panel["ordinal"],
                 next_revision, panel["role"], panel["required"], description or panel["description"],
                 panel["annotation_json"], panel["annotated_asset_id"], clean_asset_id, clean_asset_id,
                 panel["metadata_json"], timestamp, timestamp),
            )
            conn.execute("UPDATE storyboard_shots SET revision=revision+1,image_asset_id=? WHERE id=?", (clean_asset_id, panel["shot_id"]))
            conn.execute(
                """UPDATE storyboards SET revision=revision+1,updated_at=?,animatic_status='stale',
                animatic_confirmed_at=NULL,frozen_snapshot_hash=NULL WHERE id=?""",
                (timestamp, panel["storyboard_id"]),
            )
            board_revision = int(panel["board_revision"]) + 1
            _insert_workflow_event(
                conn, task_id=panel["task_id"], client_id=client_id, event_type="panel.revised",
                payload={"storyboard_id": panel["storyboard_id"], "shot_id": panel["shot_id"],
                         "panel_id": new_id, "replaces": panel_id, "version": board_revision},
            )
        result = self.get_storyboard(panel["storyboard_id"], client_id=client_id)
        assert result is not None
        return result

    def list_panel_candidates(
        self, storyboard_id: str, panel_id: str, *, client_id: str,
    ) -> dict[str, Any]:
        with self.db.transaction() as conn:
            current = conn.execute(
                """SELECT p.*,s.revision board_revision FROM storyboard_panels p
                JOIN storyboards s ON s.id=p.storyboard_id
                JOIN task_runs t ON t.id=s.task_id
                WHERE p.id=? AND p.storyboard_id=? AND p.superseded_at IS NULL
                AND t.client_id=? AND t.deleted_at IS NULL""",
                (panel_id, storyboard_id, client_id),
            ).fetchone()
            if current is None:
                raise WorkspaceNotFound("panel not found")
            rows = conn.execute(
                """SELECT * FROM storyboard_panels
                WHERE storyboard_id=? AND shot_id=? AND logical_key=?
                ORDER BY revision DESC,id""",
                (storyboard_id, current["shot_id"], current["logical_key"]),
            ).fetchall()
        candidates = []
        for row in rows:
            candidate = _decode(row)
            candidate["required"] = bool(candidate.get("required"))
            candidate["send_to_provider"] = bool(candidate.get("send_to_provider"))
            candidate["is_current"] = candidate["id"] == panel_id
            candidates.append(candidate)
        return {
            "storyboard_id": storyboard_id,
            "shot_id": current["shot_id"],
            "logical_key": current["logical_key"],
            "current_panel_id": panel_id,
            "revision": int(current["board_revision"]),
            "candidates": candidates,
        }

    def select_panel_candidate(
        self, storyboard_id: str, panel_id: str, candidate_id: str, *,
        client_id: str, expected_version: int,
    ) -> dict[str, Any]:
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            current = conn.execute(
                """SELECT p.*,s.task_id,s.revision board_revision,s.frozen_snapshot_hash
                FROM storyboard_panels p JOIN storyboards s ON s.id=p.storyboard_id
                JOIN task_runs t ON t.id=s.task_id
                WHERE p.id=? AND p.storyboard_id=? AND p.superseded_at IS NULL
                AND t.client_id=? AND t.deleted_at IS NULL""",
                (panel_id, storyboard_id, client_id),
            ).fetchone()
            if current is None:
                raise WorkspaceNotFound("panel not found")
            if int(current["board_revision"]) != expected_version:
                raise WorkspaceConflict("storyboard version changed")
            if current["frozen_snapshot_hash"]:
                raise WorkspaceConflict("approved storyboard is frozen")
            candidate = conn.execute(
                """SELECT p.* FROM storyboard_panels p
                JOIN storyboards s ON s.id=p.storyboard_id
                JOIN task_runs t ON t.id=s.task_id
                WHERE p.id=? AND t.client_id=? AND t.deleted_at IS NULL""",
                (candidate_id, client_id),
            ).fetchone()
            if candidate is None:
                raise WorkspaceNotFound("candidate not found")
            if (
                candidate["storyboard_id"] != storyboard_id
                or candidate["shot_id"] != current["shot_id"]
                or candidate["logical_key"] != current["logical_key"]
            ):
                raise WorkspaceConflict("candidate belongs to a different logical panel")
            for asset_id in (
                candidate["annotated_asset_id"], candidate["clean_asset_id"], candidate["selected_asset_id"],
            ):
                if not asset_id:
                    continue
                asset = conn.execute(
                    "SELECT id FROM assets WHERE id=? AND client_id=? AND deleted_at IS NULL",
                    (asset_id, client_id),
                ).fetchone()
                if asset is None:
                    raise WorkspaceConflict("candidate asset is unavailable")
            next_revision = int(conn.execute(
                """SELECT COALESCE(MAX(revision),0)+1 next_revision FROM storyboard_panels
                WHERE shot_id=? AND logical_key=?""",
                (current["shot_id"], current["logical_key"]),
            ).fetchone()["next_revision"])
            new_id = uuid4().hex
            metadata = _loads(candidate["metadata_json"], {})
            metadata["selected_from_panel_id"] = candidate_id
            conn.execute(
                "UPDATE storyboard_panels SET superseded_at=?,updated_at=? WHERE id=?",
                (timestamp, timestamp, panel_id),
            )
            conn.execute(
                """INSERT INTO storyboard_panels(
                id,storyboard_id,shot_id,logical_key,ordinal,revision,role,required,description,
                annotation_json,annotated_asset_id,clean_asset_id,selected_asset_id,send_to_provider,
                status,metadata_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?,?)""",
                (
                    new_id, storyboard_id, current["shot_id"], current["logical_key"], current["ordinal"],
                    next_revision, current["role"], current["required"], candidate["description"],
                    candidate["annotation_json"], candidate["annotated_asset_id"], candidate["clean_asset_id"],
                    candidate["selected_asset_id"], candidate["send_to_provider"],
                    json.dumps(metadata, ensure_ascii=False), timestamp, timestamp,
                ),
            )
            preview = conn.execute(
                """SELECT COALESCE(selected_asset_id,clean_asset_id) asset_id
                FROM storyboard_panels WHERE shot_id=? AND superseded_at IS NULL
                ORDER BY ordinal,id LIMIT 1""",
                (current["shot_id"],),
            ).fetchone()
            conn.execute(
                "UPDATE storyboard_shots SET revision=revision+1,image_asset_id=? WHERE id=?",
                (preview["asset_id"] if preview else None, current["shot_id"]),
            )
            conn.execute(
                """UPDATE storyboards SET revision=revision+1,updated_at=?,animatic_status='stale',
                animatic_confirmed_at=NULL,frozen_snapshot_hash=NULL WHERE id=?""",
                (timestamp, storyboard_id),
            )
            board_revision = int(current["board_revision"]) + 1
            _insert_workflow_event(
                conn, task_id=current["task_id"], client_id=client_id,
                event_type="panel.candidate_selected",
                payload={
                    "storyboard_id": storyboard_id, "shot_id": current["shot_id"],
                    "panel_id": new_id, "candidate_id": candidate_id,
                    "replaces": panel_id, "version": board_revision,
                },
            )
        result = self.get_storyboard(storyboard_id, client_id=client_id)
        assert result is not None
        return result

    def revise_shot_panels(
        self, storyboard_id: str, shot_id: str, *, client_id: str,
        expected_version: int, replacements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not replacements:
            raise ValueError("whole-shot revision requires replacement panels")
        replacement_by_id = {
            str(item.get("panel_id") or ""): item for item in replacements if item.get("panel_id")
        }
        if len(replacement_by_id) != len(replacements):
            raise ValueError("replacement panel ids must be unique")
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            board = conn.execute(
                """SELECT s.*,t.client_id FROM storyboards s JOIN task_runs t ON t.id=s.task_id
                WHERE s.id=? AND t.client_id=? AND t.deleted_at IS NULL""",
                (storyboard_id, client_id),
            ).fetchone()
            if board is None:
                raise WorkspaceNotFound("storyboard not found")
            if int(board["revision"]) != expected_version:
                raise WorkspaceConflict("storyboard version changed")
            if board["frozen_snapshot_hash"]:
                raise WorkspaceConflict("approved storyboard is frozen")
            shot = conn.execute(
                "SELECT * FROM storyboard_shots WHERE id=? AND storyboard_id=?",
                (shot_id, storyboard_id),
            ).fetchone()
            if shot is None:
                raise WorkspaceNotFound("shot not found")
            panels = conn.execute(
                """SELECT * FROM storyboard_panels
                WHERE storyboard_id=? AND shot_id=? AND superseded_at IS NULL
                ORDER BY ordinal,id""",
                (storyboard_id, shot_id),
            ).fetchall()
            if not panels or {panel["id"] for panel in panels} != set(replacement_by_id):
                raise WorkspaceConflict("whole-shot revision must replace every current panel")
            created: list[dict[str, Any]] = []
            for panel in panels:
                replacement = replacement_by_id[panel["id"]]
                clean_asset_id = str(replacement.get("clean_asset_id") or "")
                asset = conn.execute(
                    "SELECT id FROM assets WHERE id=? AND client_id=? AND deleted_at IS NULL",
                    (clean_asset_id, client_id),
                ).fetchone()
                if asset is None:
                    raise WorkspaceConflict("replacement panel asset is unavailable")
                next_revision = int(conn.execute(
                    """SELECT COALESCE(MAX(revision),0)+1 next_revision FROM storyboard_panels
                    WHERE shot_id=? AND logical_key=?""",
                    (shot_id, panel["logical_key"]),
                ).fetchone()["next_revision"])
                new_id = uuid4().hex
                metadata = _loads(panel["metadata_json"], {})
                metadata["regenerated_from_panel_id"] = panel["id"]
                conn.execute(
                    "UPDATE storyboard_panels SET superseded_at=?,updated_at=? WHERE id=?",
                    (timestamp, timestamp, panel["id"]),
                )
                conn.execute(
                    """INSERT INTO storyboard_panels(
                    id,storyboard_id,shot_id,logical_key,ordinal,revision,role,required,description,
                    annotation_json,annotated_asset_id,clean_asset_id,selected_asset_id,send_to_provider,
                    status,metadata_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?,?)""",
                    (
                        new_id, storyboard_id, shot_id, panel["logical_key"], panel["ordinal"],
                        next_revision, panel["role"], panel["required"],
                        str(replacement.get("description") or panel["description"]),
                        panel["annotation_json"], panel["annotated_asset_id"], clean_asset_id,
                        clean_asset_id, panel["send_to_provider"],
                        json.dumps(metadata, ensure_ascii=False), timestamp, timestamp,
                    ),
                )
                created.append({
                    "panel_id": new_id, "replaces": panel["id"],
                    "logical_key": panel["logical_key"], "revision": next_revision,
                    "clean_asset_id": clean_asset_id,
                })
            conn.execute(
                "UPDATE storyboard_shots SET revision=revision+1,image_asset_id=? WHERE id=?",
                (created[0]["clean_asset_id"], shot_id),
            )
            conn.execute(
                """UPDATE storyboards SET revision=revision+1,updated_at=?,animatic_status='stale',
                animatic_confirmed_at=NULL,frozen_snapshot_hash=NULL WHERE id=?""",
                (timestamp, storyboard_id),
            )
            board_revision = int(board["revision"]) + 1
            _insert_workflow_event(
                conn, task_id=board["task_id"], client_id=client_id,
                event_type="shot.regenerated",
                payload={
                    "storyboard_id": storyboard_id, "shot_id": shot_id,
                    "panels": created, "version": board_revision,
                },
            )
        result = self.get_storyboard(storyboard_id, client_id=client_id)
        assert result is not None
        return result

    def record_approval(
        self, *, storyboard_id: str, client_id: str, scope: str, target_id: str,
        decision: str, expected_version: int, feedback: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if scope not in {"panel", "shot", "board", "animatic"}:
            raise ValueError("unsupported approval scope")
        if decision not in {"approved", "revision_required"}:
            raise ValueError("unsupported approval decision")
        decision_id = uuid4().hex
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            board = conn.execute(
                """SELECT s.*,t.client_id FROM storyboards s JOIN task_runs t ON t.id=s.task_id
                WHERE s.id=? AND t.client_id=?""", (storyboard_id, client_id),
            ).fetchone()
            if board is None:
                raise WorkspaceNotFound("storyboard not found")
            if int(board["revision"]) != expected_version:
                raise WorkspaceConflict("storyboard version changed")
            normalized_target = target_id or storyboard_id
            if scope == "panel":
                target = conn.execute("SELECT revision FROM storyboard_panels WHERE id=? AND storyboard_id=? AND superseded_at IS NULL", (normalized_target, storyboard_id)).fetchone()
            elif scope == "shot":
                target = conn.execute("SELECT revision FROM storyboard_shots WHERE id=? AND storyboard_id=?", (normalized_target, storyboard_id)).fetchone()
            else:
                normalized_target = storyboard_id
                target = {"revision": board["revision"]}
            if target is None:
                raise WorkspaceNotFound("approval target not found")
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM approval_decisions WHERE client_id=? AND idempotency_key=?",
                    (client_id, idempotency_key),
                ).fetchone()
                if existing:
                    return _decode(existing)
            conn.execute(
                """INSERT INTO approval_decisions(
                id,task_id,storyboard_id,client_id,scope,target_id,decision,feedback,
                expected_version,target_revision,snapshot_hash,idempotency_key,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (decision_id, board["task_id"], storyboard_id, client_id, scope, normalized_target,
                 decision, feedback, expected_version, int(target["revision"]), None, idempotency_key, timestamp),
            )
            _insert_workflow_event(
                conn, task_id=board["task_id"], client_id=client_id, event_type="approval.recorded",
                payload={"storyboard_id": storyboard_id, "scope": scope, "target_id": normalized_target,
                         "decision": decision, "version": expected_version},
            )
            row = conn.execute("SELECT * FROM approval_decisions WHERE id=?", (decision_id,)).fetchone()
        return _decode(row)

    def approve_all(self, storyboard_id: str, *, client_id: str, expected_version: int) -> dict[str, Any]:
        detail = self.get_storyboard(storyboard_id, client_id=client_id)
        if detail is None:
            raise WorkspaceNotFound("storyboard not found")
        if int(detail["revision"]) != expected_version:
            raise WorkspaceConflict("storyboard version changed")
        for shot in detail["shots"]:
            for panel in shot["panels"]:
                self.record_approval(storyboard_id=storyboard_id, client_id=client_id, scope="panel",
                                     target_id=panel["id"], decision="approved", expected_version=expected_version)
            self.record_approval(storyboard_id=storyboard_id, client_id=client_id, scope="shot",
                                 target_id=shot["id"], decision="approved", expected_version=expected_version)
        self.record_approval(storyboard_id=storyboard_id, client_id=client_id, scope="board",
                             target_id=storyboard_id, decision="approved", expected_version=expected_version)
        result = self.get_storyboard(storyboard_id, client_id=client_id)
        assert result is not None
        return result

    def set_animatic(
        self, storyboard_id: str, *, client_id: str, expected_version: int,
        asset_id: str, confirmed: bool = False,
    ) -> dict[str, Any]:
        timestamp = _now()
        with self.db.transaction(immediate=True) as conn:
            board = conn.execute(
                """SELECT s.*,t.client_id FROM storyboards s JOIN task_runs t ON t.id=s.task_id
                WHERE s.id=? AND t.client_id=?""", (storyboard_id, client_id),
            ).fetchone()
            if board is None:
                raise WorkspaceNotFound("storyboard not found")
            if int(board["revision"]) != expected_version:
                raise WorkspaceConflict("storyboard version changed")
            asset = conn.execute("SELECT client_id FROM assets WHERE id=?", (asset_id,)).fetchone()
            if asset is None or asset["client_id"] != client_id:
                raise WorkspaceConflict("animatic asset has a different owner")
            status = "confirmed" if confirmed else "ready"
            conn.execute(
                """UPDATE storyboards SET animatic_asset_id=?,animatic_status=?,animatic_confirmed_at=?,
                updated_at=? WHERE id=?""", (asset_id, status, timestamp if confirmed else None, timestamp, storyboard_id),
            )
            _insert_workflow_event(
                conn, task_id=board["task_id"], client_id=client_id, event_type="animatic.ready",
                payload={"storyboard_id": storyboard_id, "asset_id": asset_id, "status": status,
                         "version": expected_version},
            )
        result = self.get_storyboard(storyboard_id, client_id=client_id)
        assert result is not None
        return result

    def confirm_animatic(self, storyboard_id: str, *, client_id: str, expected_version: int) -> dict[str, Any]:
        detail = self.get_storyboard(storyboard_id, client_id=client_id)
        if detail is None or not detail.get("animatic_asset_id"):
            raise WorkspaceConflict("animatic is not ready")
        self.record_approval(storyboard_id=storyboard_id, client_id=client_id, scope="animatic",
                             target_id=storyboard_id, decision="approved", expected_version=expected_version)
        return self.set_animatic(storyboard_id, client_id=client_id, expected_version=expected_version,
                                 asset_id=detail["animatic_asset_id"], confirmed=True)

    def freeze_storyboard(self, storyboard_id: str, *, client_id: str, expected_version: int) -> dict[str, Any]:
        detail = self.get_storyboard(storyboard_id, client_id=client_id)
        if detail is None:
            raise WorkspaceNotFound("storyboard not found")
        if int(detail["revision"]) != expected_version:
            raise WorkspaceConflict("storyboard version changed")
        if detail.get("frozen_snapshot_hash"):
            return detail
        snapshot = {
            "storyboard_id": storyboard_id, "revision": detail["revision"],
            "animatic_asset_id": detail.get("animatic_asset_id"),
            "shots": [{
                "id": shot["id"], "revision": shot["revision"], "duration_seconds": shot["duration_seconds"],
                "payload": shot.get("payload"),
                "panels": [{"id": panel["id"], "revision": panel["revision"],
                            "selected_asset_id": panel.get("selected_asset_id"),
                            "send_to_provider": panel.get("send_to_provider")} for panel in shot["panels"]],
            } for shot in detail["shots"]],
        }
        digest = _snapshot_hash(snapshot)
        with self.db.transaction(immediate=True) as conn:
            cursor = conn.execute(
                """UPDATE storyboards SET frozen_snapshot_hash=?,status='confirmed',updated_at=?
                WHERE id=? AND revision=? AND frozen_snapshot_hash IS NULL""",
                (digest, _now(), storyboard_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise WorkspaceConflict("storyboard version changed")
            task_id = conn.execute("SELECT task_id FROM storyboards WHERE id=?", (storyboard_id,)).fetchone()["task_id"]
            _insert_workflow_event(conn, task_id=task_id, client_id=client_id, event_type="storyboard.frozen",
                                   payload={"storyboard_id": storyboard_id, "version": expected_version,
                                            "snapshot_hash": digest})
        result = self.get_storyboard(storyboard_id, client_id=client_id)
        assert result is not None
        return result

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
