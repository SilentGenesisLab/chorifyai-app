from __future__ import annotations

import argparse
import secrets
from pathlib import Path

import yaml


def new_code(prefix: str) -> str:
    return f"{prefix}-{secrets.token_urlsafe(9)}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [
        {"id": f"client-{index:02d}", "code": new_code(f"HS{index}"), "client_name": f"客户{index}", "role": "client", "daily_video_limit": 40, "enabled": True}
        for index in range(1, 4)
    ]
    records.append({"id": "admin-primary", "code": new_code("HSADMIN"), "client_name": "内部管理员", "role": "admin", "daily_video_limit": 100, "enabled": True})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump({"codes": records}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(yaml.safe_dump({"codes": records}, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
