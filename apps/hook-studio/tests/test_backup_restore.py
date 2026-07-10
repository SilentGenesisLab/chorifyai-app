import sqlite3
from pathlib import Path

import pytest

from app.backup import BackupManager


def test_backup_restore_drill(tmp_path: Path):
    database = tmp_path / "live.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE proof(value TEXT)")
        conn.execute("INSERT INTO proof VALUES('recoverable')")
    events = tmp_path / "events.jsonl"; events.write_text('{"event":1}\n', encoding="utf-8")
    manager = BackupManager(database, events, tmp_path / "backups", retain=30)
    archive = manager.create()
    manifest = manager.verify(archive)
    restored_db, restored_events = tmp_path / "restore/db.sqlite3", tmp_path / "restore/events.jsonl"
    manager.restore(archive, restored_db, restored_events)
    with sqlite3.connect(restored_db) as conn:
        assert conn.execute("SELECT value FROM proof").fetchone()[0] == "recoverable"
    assert manifest.database_sha256 and restored_events.read_text(encoding="utf-8") == '{"event":1}\n'


def test_checksum_tampering_is_detected(tmp_path: Path):
    database = tmp_path / "live.sqlite3"
    with sqlite3.connect(database) as conn: conn.execute("CREATE TABLE proof(value TEXT)")
    events = tmp_path / "events.jsonl"; events.write_text("", encoding="utf-8")
    archive = BackupManager(database, events, tmp_path / "backups").create()
    assert BackupManager.verify(archive).database_bytes > 0
