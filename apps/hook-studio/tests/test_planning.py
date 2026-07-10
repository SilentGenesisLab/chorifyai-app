import pytest

from app.services.planning import normalize_plan, split_duration


@pytest.mark.parametrize(("total", "expected_count"), [(4, 1), (15, 1), (16, 2), (60, 4), (61, 5), (125, 9)])
def test_split_duration_is_unbounded_and_exact(total, expected_count):
    result = split_duration(total)
    assert len(result) == expected_count
    assert sum(result) == total
    assert all(4 <= item <= 15 for item in result)


def test_split_duration_rejects_impossible_short_video():
    with pytest.raises(ValueError):
        split_duration(3)


def test_normalize_plan_fills_missing_shots_without_fake_analysis_claim():
    shots = normalize_plan({"shots": [{"title": "钩子", "action": "按下开关，随后灯亮"}]}, brief="桌面灯", durations=[15, 15], tool="create")
    assert len(shots) == 2
    assert shots[0].title == "钩子"
    assert "桌面灯" in shots[1].visual

