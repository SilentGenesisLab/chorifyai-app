from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "node_modules", "dist", "data", "backups", "logs"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".md", ".toml", ".html", ".css", ".env", ".example"}
PATTERNS = {
    "github_token": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "bearer_literal": re.compile(r"Bearer\s+[A-Za-z0-9._-]{24,}", re.IGNORECASE),
    "private_key": re.compile(r"BEGIN (?:RSA |OPENSSH )?PRIVATE KEY"),
}


def should_scan(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    return path.name == ".env.example" or path.suffix.lower() in TEXT_SUFFIXES


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not should_scan(path.relative_to(ROOT)):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{path.relative_to(ROOT)}: {name}")
    if findings:
        print("SECRET_SCAN_FAILED")
        print("\n".join(findings))
        return 1
    print("SECRET_SCAN_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
