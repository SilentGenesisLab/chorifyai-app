from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BackupManifest:
    created_at: str
    database_name: str
    events_name: str
    database_sha256: str
    events_sha256: str
    database_bytes: int
    events_bytes: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(bundle: tarfile.TarFile, root: Path) -> None:
    allowed = {"hook-studio.sqlite3", "events.jsonl", "manifest.json"}
    members = bundle.getmembers()
    if {member.name for member in members} != allowed:
        raise ValueError("backup archive contains unexpected files")
    for member in members:
        if not member.isfile() or Path(member.name).is_absolute() or ".." in Path(member.name).parts:
            raise ValueError("unsafe backup archive member")
        source = bundle.extractfile(member)
        if source is None:
            raise ValueError("backup archive member is unreadable")
        with source, (root / member.name).open("wb") as target:
            shutil.copyfileobj(source, target)


def _sqlite_snapshot(source: Path, target: Path) -> None:
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    check = sqlite3.connect(target)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        raise RuntimeError(f"backup sqlite integrity check failed: {result}")


class BackupManager:
    def __init__(self, database_path: str | Path, events_path: str | Path, backup_dir: str | Path, *, uploader: Any | None = None, retain: int = 30):
        self.database_path = Path(database_path)
        self.events_path = Path(events_path)
        self.backup_dir = Path(backup_dir)
        self.uploader = uploader
        self.retain = retain

    def create(self, *, now: datetime | None = None) -> Path:
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        archive = self.backup_dir / f"hook-studio-{stamp}.tar.gz"
        with tempfile.TemporaryDirectory(prefix="hook-backup-") as temp:
            root = Path(temp)
            database = root / "hook-studio.sqlite3"
            events = root / "events.jsonl"
            _sqlite_snapshot(self.database_path, database)
            if self.events_path.exists():
                shutil.copy2(self.events_path, events)
            else:
                events.write_text("", encoding="utf-8")
            manifest = BackupManifest(
                created_at=(now or datetime.now(timezone.utc)).isoformat(),
                database_name=database.name, events_name=events.name,
                database_sha256=_sha256(database), events_sha256=_sha256(events),
                database_bytes=database.stat().st_size, events_bytes=events.stat().st_size,
            )
            (root / "manifest.json").write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
            with tarfile.open(archive, "w:gz") as bundle:
                for path in (database, events, root / "manifest.json"):
                    bundle.add(path, arcname=path.name)
        self._prune_local()
        return archive

    async def upload(self, archive: Path) -> str | None:
        if self.uploader is None:
            return None
        key = f"hook-studio/backups/{archive.name}"
        result = self.uploader.upload(archive, key)
        if hasattr(result, "__await__"):
            result = await result
        return str(result)

    def _prune_local(self) -> None:
        archives = sorted(self.backup_dir.glob("hook-studio-*.tar.gz"), reverse=True)
        for path in archives[self.retain:]:
            path.unlink()

    @staticmethod
    def verify(archive: str | Path) -> BackupManifest:
        with tempfile.TemporaryDirectory(prefix="hook-verify-") as temp:
            root = Path(temp)
            with tarfile.open(archive, "r:gz") as bundle:
                members = bundle.getmembers()
                if any(Path(member.name).is_absolute() or ".." in Path(member.name).parts for member in members):
                    raise ValueError("unsafe backup archive path")
                _extract(bundle, root)
            data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest = BackupManifest(**data)
            database = root / manifest.database_name
            events = root / manifest.events_name
            if _sha256(database) != manifest.database_sha256 or _sha256(events) != manifest.events_sha256:
                raise ValueError("backup checksum mismatch")
            conn = sqlite3.connect(database)
            try:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("backup database integrity check failed")
            finally:
                conn.close()
            return manifest

    @classmethod
    def restore(cls, archive: str | Path, database_target: str | Path, events_target: str | Path) -> BackupManifest:
        manifest = cls.verify(archive)
        with tempfile.TemporaryDirectory(prefix="hook-restore-") as temp:
            root = Path(temp)
            with tarfile.open(archive, "r:gz") as bundle:
                members = bundle.getmembers()
                if any(Path(member.name).is_absolute() or ".." in Path(member.name).parts for member in members):
                    raise ValueError("unsafe backup archive path")
                _extract(bundle, root)
            db_target, log_target = Path(database_target), Path(events_target)
            db_target.parent.mkdir(parents=True, exist_ok=True)
            log_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / manifest.database_name, db_target)
            shutil.copy2(root / manifest.events_name, log_target)
        return manifest
