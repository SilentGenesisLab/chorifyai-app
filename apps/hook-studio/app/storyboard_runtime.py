from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class PanelContract:
    logical_key: str
    ordinal: int
    role: str
    required: bool
    description: str
    annotation: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShotContract:
    id: str
    ordinal: int
    duration_seconds: int
    title: str
    story_function: str
    visual: str
    shot_size: str
    camera_angle: str
    camera_height: str
    lens_feel: str
    composition: str
    action_start: str
    action_trigger: str
    action_result: str
    camera_move: str
    sound: str
    transition: str
    stable_truth: list[str]
    may_vary: list[str]
    reference_manifest: list[dict[str, Any]]
    first_failure_cue: str
    prompt: str

    @classmethod
    def from_plan(cls, plan: Any) -> "ShotContract":
        value = plan.as_dict() if hasattr(plan, "as_dict") else dict(plan)
        action = str(value.get("action") or "主体完成一个清晰动作并展示结果")
        return cls(
            id=str(value.get("id") or uuid4().hex),
            ordinal=int(value.get("ordinal") or 1),
            duration_seconds=int(value.get("duration_seconds") or value.get("duration") or 5),
            title=str(value.get("title") or "镜头"),
            story_function=str(value.get("story_function") or value.get("purpose") or "推进叙事"),
            visual=str(value.get("visual") or value.get("description") or "主体清晰可见"),
            shot_size=str(value.get("shot_size") or "近景"),
            camera_angle=str(value.get("camera_angle") or "平视"),
            camera_height=str(value.get("camera_height") or "主体中心高度"),
            lens_feel=str(value.get("lens_feel") or "35mm真实摄影感"),
            composition=str(value.get("composition") or "主体位于9:16安全区中央，前中后景清楚"),
            action_start=str(value.get("action_start") or f"动作开始前，{value.get('visual') or '主体保持稳定'}"),
            action_trigger=str(value.get("action_trigger") or action),
            action_result=str(value.get("action_result") or "动作完成，结果清楚且可验证"),
            camera_move=str(value.get("camera_move") or value.get("camera") or "稳定的单一连续运镜"),
            sound=str(value.get("sound") or "动作同步环境音和动作音"),
            transition=str(value.get("transition") or "按动作完成点切镜"),
            stable_truth=list(value.get("stable_truth") or ["产品结构", "主体身份", "空间方向"]),
            may_vary=list(value.get("may_vary") or ["手部微动作", "环境细节"]),
            reference_manifest=list(value.get("reference_manifest") or []),
            first_failure_cue=str(value.get("first_failure_cue") or "主体结构、动作因果或空间方向首先发生漂移"),
            prompt=str(value.get("prompt") or ""),
        )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["description"] = self.visual
        value["duration"] = self.duration_seconds
        value["purpose"] = self.story_function
        value["action"] = f"{self.action_start}；{self.action_trigger}；{self.action_result}"
        value["camera"] = self.camera_move
        return value

