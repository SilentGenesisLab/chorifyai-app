from app.build_info import build_info


def test_build_info_normalizes_missing_and_long_values(monkeypatch):
    monkeypatch.delenv("HOOK_STUDIO_BUILD_SHA", raising=False)
    monkeypatch.setenv("HOOK_STUDIO_SCHEMA_VERSION", "full-storyboard-v1")
    monkeypatch.setenv("HOOK_STUDIO_SKILL_PACK_VERSION", "hook-production-3.0.0")
    assert build_info() == {
        "build_sha": "unknown",
        "schema_version": "full-storyboard-v1",
        "skill_pack_version": "hook-production-3.0.0",
    }


def test_build_info_rejects_control_characters(monkeypatch):
    monkeypatch.setenv("HOOK_STUDIO_BUILD_SHA", "abc\nsecret")
    assert build_info()["build_sha"] == "invalid"
