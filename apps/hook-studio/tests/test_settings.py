from pathlib import Path

import pytest

from app.settings import Settings


def test_settings_load_and_resolve_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOOK_STUDIO_DATA_DIR", "runtime")
    monkeypatch.setenv("HOOK_STUDIO_ACCESS_CODES_FILE", "secrets/codes.yaml")
    settings = Settings.from_env()
    assert settings.data_dir == (tmp_path / "runtime").resolve()
    assert settings.database_path.name == "hook-studio.sqlite3"
    assert settings.global_video_daily_limit == 100
    assert settings.image_concurrency == settings.video_concurrency == 2


def test_production_requires_long_session_secret(monkeypatch):
    monkeypatch.setenv("HOOK_STUDIO_ENV", "production")
    monkeypatch.setenv("HOOK_STUDIO_SESSION_SECRET", "short")
    with pytest.raises(ValueError, match="32"):
        Settings.from_env()


def test_base_path_rejects_trailing_slash(monkeypatch):
    monkeypatch.setenv("HOOK_STUDIO_BASE_PATH", "/hook-studio/")
    with pytest.raises(ValueError, match="trailing"):
        Settings.from_env()

