from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from app.storyboard_runtime import PanelContract, ShotContract


SKILL_PACK_VERSION = "full-storyboard-v1.0.0"


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProductionGateError(ValueError):
    code = "STORYBOARD_GATE_BLOCKED"

    def __init__(self, reasons: Iterable[str]):
        self.reasons = list(reasons)
        super().__init__("；".join(self.reasons) or "故事板生产门禁未通过")


class BriefCompiler:
    skill_id = "brief-compiler"
    version = "1.0.0"

    def compile(self, prompt: str, context: str = "") -> dict[str, Any]:
        return {"brief": prompt.strip(), "context": context.strip(), "ratio": "9:16"}


class StoryboardCompiler:
    skill_id = "storyboard-compiler"
    version = "1.0.0"

    def compile(self, plans: Iterable[Any]) -> list[ShotContract]:
        return [ShotContract.from_plan(plan) for plan in plans]


class PanelPlanner:
    skill_id = "panel-planner"
    version = "1.0.0"

    def plan(self, shot: ShotContract) -> list[PanelContract]:
        return [
            PanelContract("start", 1, "start", True, shot.action_start, {"label": "动作起点", "camera": shot.camera_move}),
            PanelContract("action", 2, "action", True, shot.action_trigger, {"label": "动作变化", "camera": shot.camera_move}),
            PanelContract("result", 3, "result", True, shot.action_result, {"label": "动作结果", "camera": shot.camera_move}),
        ]


class ReferenceManifestCompiler:
    skill_id = "reference-manifest-compiler"
    version = "1.0.0"

    def compile(self, image_urls: list[str], video_urls: list[str] | None = None) -> list[dict[str, Any]]:
        manifest = [
            {"kind": "image", "slot": index + 1, "url": url, "role": "产品或主体身份", "controls": ["外观", "身份"], "must_not_control": ["镜头运动"]}
            for index, url in enumerate(image_urls)
        ]
        manifest.extend(
            {"kind": "video", "slot": index + 1, "url": url, "role": "结构与动作参考", "controls": ["动作因果", "节奏"], "must_not_control": ["原人物", "品牌", "字幕", "音乐"]}
            for index, url in enumerate(video_urls or [])
        )
        return manifest


class PromptCompiler:
    skill_id = "prompt-compiler"
    version = "1.0.0"

    def compile(self, shot: ShotContract, panel: PanelContract) -> str:
        return (
            f"9:16真实商业摄影分镜，{shot.shot_size}，{shot.camera_angle}，{shot.camera_height}，"
            f"{shot.lens_feel}。构图：{shot.composition}。当前Panel是{panel.annotation.get('label')}："
            f"{panel.description}。保持：{'、'.join(shot.stable_truth)}。允许变化：{'、'.join(shot.may_vary)}。"
            "单一明确状态，无字幕、无箭头、无网格、无水印。"
        )


class ShotGateValidator:
    skill_id = "shot-gate-validator"
    version = "1.0.0"

    def require(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        shots = list(snapshot.get("shots") or [])
        if not shots:
            reasons.append("故事板没有镜头")
        for shot in shots:
            label = f"镜头{shot.get('ordinal') or shot.get('id')}"
            duration = float(shot.get("duration_seconds") or 0)
            if duration < 4 or duration > 15:
                reasons.append(f"{label}时长必须为4-15秒")
            if not isinstance((shot.get("payload") or {}).get("reference_manifest"), list):
                reasons.append(f"{label}缺少引用清单")
            panels = list(shot.get("panels") or [])
            required = [panel for panel in panels if panel.get("required")]
            if not required:
                reasons.append(f"{label}缺少必需Panel")
            for panel in required:
                if not panel.get("selected_asset_id") or not panel.get("send_to_provider"):
                    reasons.append(f"{label}存在未选择的clean frame")
                if not panel.get("approved"):
                    reasons.append(f"{label}存在未批准Panel")
            if not shot.get("approved"):
                reasons.append(f"{label}尚未逐镜批准")
        if not snapshot.get("board_approved"):
            reasons.append("整板尚未批准")
        if snapshot.get("animatic_status") != "confirmed":
            reasons.append("动态预演尚未确认")
        if reasons:
            raise ProductionGateError(reasons)
        return {"passed": True, "shot_count": len(shots), "panel_count": sum(len(item.get("panels") or []) for item in shots)}


class ApprovalPolicy(ShotGateValidator):
    skill_id = "approval-policy"


@dataclass
class SkillRuntime:
    repository: Any

    def execute(
        self, *, task_id: str, skill_id: str, skill_version: str, stage: str,
        public_label: str, inputs: Any, operation: Callable[[], Any],
        storyboard_id: str | None = None, shot_id: str | None = None,
        blocking: bool = False, retry_count: int = 0,
    ) -> Any:
        started = time.perf_counter()
        status = "passed"
        reason = ""
        try:
            output = operation()
            return output
        except Exception as exc:
            status = "blocked" if blocking else "failed"
            reason = str(exc)
            output = {"error": reason}
            raise
        finally:
            self.repository.record_skill_run(
                task_id=task_id, storyboard_id=storyboard_id, shot_id=shot_id,
                skill_id=skill_id, skill_version=skill_version, stage=stage, status=status,
                blocking=blocking, public_label=public_label, input_hash=stable_hash(inputs),
                output_hash=stable_hash(output), input_count=_count(inputs), output_count=_count(output),
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)), retry_count=retry_count,
                blocking_reason=reason or None, evidence={"pack_version": SKILL_PACK_VERSION},
                private_trace={"input_type": type(inputs).__name__, "output_type": type(output).__name__},
            )


def _count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    return 1

