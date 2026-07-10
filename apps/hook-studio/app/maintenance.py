from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app.backup import BackupManager
from app.db import Database
from app.insights import InsightsService
from app.main import KernelBackupUploader
from app.providers.kernel import KernelProvider
from app.settings import Settings


async def run() -> None:
    settings = Settings.from_env()
    db = Database(settings.database_path)
    db.initialize()
    provider = KernelProvider(settings.kernel_base_url, settings.kernel_bearer, timeout_seconds=90)
    manager = BackupManager(
        settings.database_path, settings.events_path, settings.data_dir / "backups",
        uploader=KernelBackupUploader(provider),
    )
    archive = manager.create()
    manifest = manager.verify(archive)
    url = await manager.upload(archive)
    status = {"created_at": manifest.created_at, "archive": archive.name, "oss_url": url, "verified": True}
    insights = InsightsService(db)
    output = settings.data_dir / "insights"
    insights.write_hook_insights(output)
    (output / "WEEKLY_DEMO_DIGEST.md").write_text(insights.render_digest(), encoding="utf-8")
    with db.transaction(immediate=True) as conn:
        conn.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES('last_backup',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (json.dumps(status, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())
