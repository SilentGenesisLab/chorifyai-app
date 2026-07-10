from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


@dataclass(frozen=True, slots=True)
class Settings:
    env: str
    base_path: str
    data_dir: Path
    access_codes_file: Path
    session_secret: str
    session_ttl_seconds: int
    cookie_secure: bool
    global_video_daily_limit: int
    global_image_daily_limit: int
    image_concurrency: int
    video_concurrency: int
    production_concurrency: int
    provider_mode: str
    kernel_base_url: str
    kernel_bearer: str | None
    tts_base_url: str
    internal_api_key: str | None
    default_tts_voice: str
    crawler_base_url: str
    crawler_api_key: str | None
    asr_api_key: str | None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "hook-studio.sqlite3"

    @property
    def events_path(self) -> Path:
        return self.data_dir / "events.jsonl"

    @classmethod
    def from_env(cls) -> "Settings":
        get = lambda name, default: os.getenv(f"HOOK_STUDIO_{name}", default)
        base_path = get("BASE_PATH", "/hook-studio").strip()
        if not base_path.startswith("/") or (base_path != "/" and base_path.endswith("/")):
            raise ValueError("HOOK_STUDIO_BASE_PATH must start with / and have no trailing slash")
        settings = cls(
            env=get("ENV", "development"),
            base_path=base_path,
            data_dir=Path(get("DATA_DIR", "./data")).expanduser().resolve(),
            access_codes_file=Path(get("ACCESS_CODES_FILE", "./config/access_codes.yaml")).expanduser().resolve(),
            session_secret=get("SESSION_SECRET", "development-only-change-me"),
            session_ttl_seconds=int(get("SESSION_TTL_SECONDS", "43200")),
            cookie_secure=_bool_env(get("COOKIE_SECURE", "false")),
            global_video_daily_limit=int(get("GLOBAL_VIDEO_DAILY_LIMIT", "100")),
            global_image_daily_limit=int(get("GLOBAL_IMAGE_DAILY_LIMIT", "100000")),
            image_concurrency=int(get("IMAGE_CONCURRENCY", "2")),
            video_concurrency=int(get("VIDEO_CONCURRENCY", "2")),
            production_concurrency=int(get("PRODUCTION_CONCURRENCY", "2")),
            provider_mode=get("PROVIDER_MODE", "kernel").strip().lower(),
            kernel_base_url=get("KERNEL_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            kernel_bearer=os.getenv("HOOK_STUDIO_KERNEL_BEARER") or None,
            tts_base_url=get("TTS_BASE_URL", "http://120.26.95.170:8544").rstrip("/"),
            internal_api_key=os.getenv("HOOK_STUDIO_INTERNAL_API_KEY") or None,
            default_tts_voice=get("DEFAULT_TTS_VOICE", "zh_male_m191_uranus_bigtts"),
            crawler_base_url=get("CRAWLER_BASE_URL", "http://121.15.184.231:6080").rstrip("/"),
            crawler_api_key=os.getenv("HOOK_STUDIO_CRAWLER_API_KEY") or None,
            asr_api_key=os.getenv("HOOK_STUDIO_ASR_API_KEY") or None,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.env != "development" and len(self.session_secret) < 32:
            raise ValueError("HOOK_STUDIO_SESSION_SECRET must contain at least 32 characters")
        for name, value in (
            ("SESSION_TTL_SECONDS", self.session_ttl_seconds),
            ("GLOBAL_VIDEO_DAILY_LIMIT", self.global_video_daily_limit),
            ("GLOBAL_IMAGE_DAILY_LIMIT", self.global_image_daily_limit),
            ("IMAGE_CONCURRENCY", self.image_concurrency),
            ("VIDEO_CONCURRENCY", self.video_concurrency),
            ("PRODUCTION_CONCURRENCY", self.production_concurrency),
        ):
            if value <= 0:
                raise ValueError(f"HOOK_STUDIO_{name} must be positive")
        if self.provider_mode not in {"kernel", "fake"}:
            raise ValueError("HOOK_STUDIO_PROVIDER_MODE must be kernel or fake")
