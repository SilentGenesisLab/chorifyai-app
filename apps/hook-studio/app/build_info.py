from __future__ import annotations

import os


def _public_value(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()[:96]
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return "invalid"
    return value


def build_info() -> dict[str, str]:
    """Return non-secret release identity for health checks and operators."""

    return {
        "build_sha": _public_value("HOOK_STUDIO_BUILD_SHA", "unknown"),
        "schema_version": _public_value("HOOK_STUDIO_SCHEMA_VERSION", "3"),
        "skill_pack_version": _public_value("HOOK_STUDIO_SKILL_PACK_VERSION", "full-storyboard-v1.0.0"),
    }
