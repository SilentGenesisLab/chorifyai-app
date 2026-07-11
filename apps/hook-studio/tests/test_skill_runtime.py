from __future__ import annotations

import pytest

from app.skill_runtime import PanelPlanner, ProductionGateError, ShotGateValidator, StoryboardCompiler
from app.services.planning import normalize_plan
from app.services.production import ProductionManager


def test_storyboard_compiler_produces_complete_shot_contract_and_panels():
    plans = normalize_plan({"shots": [{"title": "开场", "visual": "桌面上的产品"}]}, brief="展示桌面灯", durations=[5], tool="create")
    contract = StoryboardCompiler().compile(plans)[0]
    assert contract.story_function
    assert contract.action_start and contract.action_trigger and contract.action_result
    assert contract.shot_size and contract.camera_angle and contract.composition
    panels = PanelPlanner().plan(contract)
    assert [panel.role for panel in panels] == ["start", "action", "result"]
    assert all(panel.required for panel in panels)


@pytest.mark.parametrize("missing", ["panels", "clean", "panel_approval", "shot_approval", "animatic"])
def test_gate_fails_closed_for_incomplete_storyboard(missing):
    snapshot = {
        "revision": 1, "animatic_status": "confirmed", "board_approved": True,
        "shots": [{
            "id": "s1", "duration_seconds": 5, "revision": 1, "approved": True,
            "payload": {"reference_manifest": []},
            "panels": [{"id": "p1", "required": True, "revision": 1, "approved": True,
                        "selected_asset_id": "a1", "send_to_provider": True}],
        }],
    }
    if missing == "panels": snapshot["shots"][0]["panels"] = []
    if missing == "clean": snapshot["shots"][0]["panels"][0]["selected_asset_id"] = None
    if missing == "panel_approval": snapshot["shots"][0]["panels"][0]["approved"] = False
    if missing == "shot_approval": snapshot["shots"][0]["approved"] = False
    if missing == "animatic": snapshot["animatic_status"] = "ready"
    with pytest.raises(ProductionGateError):
        ShotGateValidator().require(snapshot)


def test_panel_reference_chain_keeps_previous_clean_frame_in_last_slot():
    assert ProductionManager._panel_references(["product", "person"], None) == ["product", "person"]
    assert ProductionManager._panel_references(["product", "person"], "previous-clean") == ["product", "person", "previous-clean"]
    assert ProductionManager._panel_references([f"ref-{index}" for index in range(9)], "previous-clean")[-1] == "previous-clean"
