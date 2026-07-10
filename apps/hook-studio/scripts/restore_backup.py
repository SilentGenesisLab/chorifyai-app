from __future__ import annotations

import argparse
from pathlib import Path

from app.backup import BackupManager
from app.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify and restore a Hook Studio backup")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = BackupManager.verify(args.archive)
    if args.verify_only:
        print(f"verified: {args.archive.name} ({manifest.created_at})")
        return
    settings = Settings.from_env()
    BackupManager.restore(args.archive, settings.database_path, settings.events_path)
    print(f"restored: {args.archive.name} -> {settings.data_dir}")


if __name__ == "__main__":
    main()
