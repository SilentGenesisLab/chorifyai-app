from pathlib import Path

import pytest

from app.skill_policy import SkillGateBlocked, VideoSkillPolicy


POLICY = Path(__file__).parents[1] / "config" / "skill-policy-v1.yaml"


def test_video_policy_records_all_hard_checks():
    policy = VideoSkillPolicy.from_file(POLICY)
    prompt = "美区厨房中，当用户按下产品按钮，随后产品打开，同时保留原生环境音和动作音，不出现水印。"
    trace = policy.require(prompt=prompt, duration=4, ratio="9:16", reference_urls=["https://x/p.png"], slot_manifest=[{"slot": 1, "url": "https://x/p.png", "role": "产品身份"}])
    assert trace.passed
    assert len(trace.checks) == 6
    assert trace.version == "2.0.0"


def test_video_policy_accepts_every_supported_single_shot_duration():
    policy = VideoSkillPolicy.from_file(POLICY)
    prompt = "美区厨房中，当用户按下产品按钮，随后产品打开，同时保留原生环境音和动作音，不出现水印。"
    for duration in range(4, 16):
        assert policy.require(prompt=prompt, duration=duration, ratio="9:16").passed


def test_video_policy_fails_closed_without_audio_and_manifest():
    policy = VideoSkillPolicy.from_file(POLICY)
    with pytest.raises(SkillGateBlocked) as error:
        policy.require(prompt="用户随后打开产品并展示结果", duration=4, ratio="9:16", reference_urls=["https://x/p.png"], slot_manifest=[])
    failed = {check.id for check in error.value.trace.checks if check.status == "fail"}
    assert {"slot-order", "reference-role", "native-audio-intent"} <= failed


def test_video_policy_allows_one_negation_to_cover_a_prohibited_list():
    policy = VideoSkillPolicy.from_file(POLICY)
    trace = policy.require(
        prompt="当用户按下开关，随后产品亮起。保留原生环境音和动作音，不出现字幕、水印或竞品logo。",
        duration=5, ratio="9:16", reference_urls=[], slot_manifest=[],
    )
    assert trace.passed
