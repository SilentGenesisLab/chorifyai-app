from app.skill_runtime import ImageRouterCompiler


def test_router_keeps_ui_concept_separate_from_runnable_ui():
    packet = ImageRouterCompiler().compile("生成一个移动端 UI/UX 高保真概念图，9:16")
    assert packet["domain"] == "ui_ux"
    assert packet["fidelity_label"] == "CONCEPT_ONLY"
    assert packet["aspect_ratio"] == "9:16"
    assert "不得宣称" in packet["prompt_final"]


def test_router_compiles_optional_mask_and_annotation_roles():
    packet = ImageRouterCompiler().compile(
        "把蓝色卡片改成绿色",
        action="edit",
        assets=[{"id": "source", "role": "edit_target"}, {"id": "note", "role": "annotation"}],
        has_mask=True,
        has_annotation=True,
    )
    assert packet["fidelity_label"] == "LOCAL_EDIT"
    assert packet["qc_contract"]["outside_mask_pixels_unchanged"] is True
    assert "箭头" in packet["prompt_final"]
    assert packet["fallback_plan"] == ["reference_repaint", "mask_pixel_composite"]


def test_mask_does_not_shift_visual_reference_numbers():
    packet = ImageRouterCompiler().compile(
        "按照定位图修改颜色", action="edit",
        assets=[
            {"id": "source", "role": "edit_target"},
            {"id": "mask", "role": "mask"},
            {"id": "annotation", "role": "annotation"},
        ],
        has_mask=True, has_annotation=True,
    )
    assert "图1只作为edit_target" in packet["prompt_final"]
    assert "图2只作为annotation" in packet["prompt_final"]
    assert "图3" not in packet["prompt_final"]
    assert "蒙版单独定义" in packet["prompt_final"]


def test_visual_reference_numbers_follow_provider_role_order_not_upload_order():
    packet = ImageRouterCompiler().compile(
        "按照定位图修改颜色", action="edit",
        assets=[
            {"id": "annotation", "role": "annotation"},
            {"id": "mask", "role": "mask"},
            {"id": "source", "role": "edit_target"},
        ],
        has_mask=True, has_annotation=True,
    )
    prompt = packet["prompt_final"]
    assert prompt.index("图1只作为edit_target") < prompt.index("图2只作为annotation")
