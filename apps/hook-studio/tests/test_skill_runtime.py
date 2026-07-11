from __future__ import annotations

import pytest

from app.skill_runtime import PanelPlanner, ProductionGateError, ShotGateValidator, StoryboardCompiler
from app.services.planning import normalize_plan
from app.services.production import ProductionManager


def _snapshot(reference_manifest=None):
    payload = {
        "story_function": "建立钩子", "visual": "产品进入画面", "shot_size": "近景",
        "camera_angle": "平视", "camera_height": "桌面高度", "lens_feel": "35mm",
        "composition": "产品居中", "action_start": "空桌面", "action_trigger": "手拿产品进入",
        "action_result": "产品居中", "camera_move": "缓慢推近", "sound": "环境音",
        "transition": "硬切", "stable_truth": ["产品外观"], "may_vary": ["手部位置"],
        "reference_manifest": [] if reference_manifest is None else reference_manifest,
        "first_failure_cue": "产品结构漂移",
    }
    return {
        "revision": 1, "animatic_status": "confirmed", "board_approved": True,
        "shots": [{
            "id": "s1", "duration_seconds": 5, "revision": 1, "approved": True,
            "payload": payload,
            "panels": [
                {"id": f"p-{role}", "role": role, "required": True, "revision": 1,
                 "approved": True, "clean_asset_id": f"a{ordinal}",
                 "selected_asset_id": f"a{ordinal}", "send_to_provider": True}
                for ordinal, role in enumerate(("start", "action", "result"), start=1)
            ],
        }],
    }


def _ready_clean(storage_uri="https://cdn.example/clean.png", **overrides):
    return {
        "client_id": "client-a", "source_type": "storyboard_clean", "media_type": "image",
        "status": "ready", "storage_uri": storage_uri, **overrides,
    }


def test_storyboard_compiler_produces_complete_shot_contract_and_panels():
    plans = normalize_plan({"shots": [{"title": "开场", "visual": "桌面上的产品"}]}, brief="展示桌面灯", durations=[5], tool="create")
    contract = StoryboardCompiler().compile(plans)[0]
    assert contract.story_function
    assert contract.action_start and contract.action_trigger and contract.action_result
    assert contract.shot_size and contract.camera_angle and contract.composition
    panels = PanelPlanner().plan(contract)
    assert [panel.role for panel in panels] == ["start", "result"]
    assert all(panel.required for panel in panels)


@pytest.mark.parametrize("missing", ["panels", "clean", "panel_approval", "shot_approval"])
def test_gate_fails_closed_for_incomplete_storyboard(missing):
    snapshot = _snapshot()
    if missing == "panels": snapshot["shots"][0]["panels"] = []
    if missing == "clean": snapshot["shots"][0]["panels"][0]["selected_asset_id"] = None
    if missing == "panel_approval": snapshot["shots"][0]["panels"][0]["approved"] = False
    if missing == "shot_approval": snapshot["shots"][0]["approved"] = False
    with pytest.raises(ProductionGateError):
        ShotGateValidator().require(snapshot)


def test_gate_accepts_complete_storyboard_with_tenant_scoped_ready_assets():
    result = ShotGateValidator().require(
        _snapshot(), resolve_asset=lambda _asset_id: _ready_clean(),
        resolve_reference=lambda _kind, _url: None,
    )
    assert result == {"passed": True, "shot_count": 1, "panel_count": 3}


def test_gate_allows_no_animatic_but_requires_confirmation_when_one_exists():
    snapshot = _snapshot()
    snapshot["animatic_status"] = "missing"
    assert ShotGateValidator().require(snapshot)["passed"]
    snapshot["animatic_status"] = "ready"
    with pytest.raises(ProductionGateError, match="动态预演"):
        ShotGateValidator().require(snapshot)


@pytest.mark.parametrize("manifest", [
    ["not-an-object"],
    [{"kind": "image", "slot": 1, "url": "https://cdn.example/ref.png",
      "role": "主体身份", "controls": ["外观"], "must_not_control": ["运镜"],
      "provider": "SecretProvider", "model": "SecretModel"}],
    [{"kind": "image", "slot": 1, "role": "主体身份",
      "controls": ["外观"], "must_not_control": ["运镜"]}],
    [{"kind": "image", "slot": 1, "url": "file:///etc/passwd", "role": "主体身份",
      "controls": ["外观"], "must_not_control": ["运镜"]}],
])
def test_reference_manifest_rejects_invalid_structure_fields_and_urls(manifest):
    with pytest.raises(ProductionGateError):
        ShotGateValidator().require(_snapshot(manifest))


def test_reference_manifest_rejects_cross_tenant_or_unready_assets():
    manifest = [{
        "kind": "image", "slot": 1, "url": "https://cdn.example/ref.png",
        "role": "主体身份", "controls": ["外观"], "must_not_control": ["运镜"],
    }]
    with pytest.raises(ProductionGateError, match="当前客户"):
        ShotGateValidator().require(
            _snapshot(manifest),
            resolve_asset=lambda _asset_id: _ready_clean(),
            resolve_reference=lambda _kind, _url: None,
        )
    with pytest.raises(ProductionGateError, match="状态不可用"):
        ShotGateValidator().require(
            _snapshot(manifest),
            resolve_asset=lambda _asset_id: _ready_clean(),
            resolve_reference=lambda _kind, url: {
                **_ready_clean(url), "source_type": "upload", "status": "processing",
            },
        )


@pytest.mark.parametrize("asset", [
    _ready_clean(status="processing"),
    _ready_clean(storage_uri=None),
    _ready_clean(source_type="storyboard_annotated"),
    _ready_clean(media_type="video"),
    None,
])
def test_selected_clean_frame_must_be_ready_readable_and_clean(asset):
    with pytest.raises(ProductionGateError):
        ShotGateValidator().require(
            _snapshot(), resolve_asset=lambda _asset_id: asset,
        )


def test_panel_reference_chain_keeps_previous_clean_frame_in_last_slot():
    assert ProductionManager._panel_references(["product", "person"], None) == ["product", "person"]
    assert ProductionManager._panel_references(["product", "person"], "previous-clean") == ["product", "person", "previous-clean"]
    assert ProductionManager._panel_references([f"ref-{index}" for index in range(9)], "previous-clean")[-1] == "previous-clean"
