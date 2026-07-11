from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from app.storyboard_runtime import PanelContract, ShotContract


SKILL_PACK_VERSION = "full-storyboard-v1.0.0"
REFERENCE_MANIFEST_FIELDS = frozenset({
    "kind", "slot", "url", "role", "controls", "must_not_control",
})
REFERENCE_MANIFEST_KINDS = {"image": 9, "video": 3}
REQUIRED_PANEL_ROLES = frozenset({"start", "action", "result"})
REQUIRED_SHOT_TEXT_FIELDS = (
    "story_function", "visual", "shot_size", "camera_angle", "camera_height",
    "lens_feel", "composition", "action_start", "action_trigger", "action_result",
    "camera_move", "sound", "transition", "first_failure_cue",
)


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

    def require(
        self, snapshot: dict[str, Any], *,
        resolve_asset: Callable[[str], dict[str, Any] | None] | None = None,
        resolve_reference: Callable[[str, str], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        reasons: list[str] = []
        shots = list(snapshot.get("shots") or [])
        if not shots:
            reasons.append("故事板没有镜头")
        for shot in shots:
            label = f"镜头{shot.get('ordinal') or shot.get('id')}"
            duration = float(shot.get("duration_seconds") or 0)
            if duration < 4 or duration > 15:
                reasons.append(f"{label}时长必须为4-15秒")
            payload = shot.get("payload") or {}
            for field in REQUIRED_SHOT_TEXT_FIELDS:
                if not isinstance(payload.get(field), str) or not payload[field].strip():
                    reasons.append(f"{label}缺少完整镜头字段：{field}")
            for field in ("stable_truth", "may_vary"):
                value = payload.get(field)
                if not isinstance(value, list) or not value or not all(
                    isinstance(item, str) and item.strip() for item in value
                ):
                    reasons.append(f"{label}缺少完整镜头字段：{field}")
            self._validate_reference_manifest(
                payload.get("reference_manifest"), label=label,
                resolve_reference=resolve_reference, reasons=reasons,
            )
            panels = list(shot.get("panels") or [])
            roles = {
                str(panel.get("role") or "") for panel in panels
                if isinstance(panel, dict) and panel.get("required")
            }
            if len(panels) < 3 or not REQUIRED_PANEL_ROLES.issubset(roles):
                reasons.append(f"{label}缺少start/action/result必需Panel")
            required = [panel for panel in panels if panel.get("required")]
            if not required:
                reasons.append(f"{label}缺少必需Panel")
            for panel in panels:
                must_send = bool(panel.get("required") or panel.get("send_to_provider"))
                if not must_send:
                    continue
                asset_id = str(panel.get("selected_asset_id") or "")
                if not asset_id or not panel.get("send_to_provider"):
                    reasons.append(f"{label}存在未选择的clean frame")
                if not panel.get("approved"):
                    reasons.append(f"{label}存在未批准Panel")
                if panel.get("annotated_asset_id") and panel.get("annotated_asset_id") == panel.get("selected_asset_id"):
                    reasons.append(f"{label}的标注板禁止发送到生成服务")
                if resolve_asset is not None and asset_id:
                    asset = resolve_asset(asset_id)
                    if asset is None:
                        reasons.append(f"{label}的clean frame不属于当前客户或已删除")
                    elif asset.get("media_type") != "image":
                        reasons.append(f"{label}的clean frame必须是图片")
                    elif asset.get("source_type") != "storyboard_clean":
                        reasons.append(f"{label}选择的不是clean frame")
                    elif asset.get("status") != "ready":
                        reasons.append(f"{label}的clean frame状态不可用")
                    elif not _is_sendable_url(asset.get("storage_uri")):
                        reasons.append(f"{label}的clean frame缺少可读取URI")
            if not shot.get("approved"):
                reasons.append(f"{label}尚未逐镜批准")
        if not snapshot.get("board_approved"):
            reasons.append("整板尚未批准")
        if snapshot.get("animatic_status") != "confirmed":
            reasons.append("动态预演尚未确认")
        if reasons:
            raise ProductionGateError(reasons)
        return {"passed": True, "shot_count": len(shots), "panel_count": sum(len(item.get("panels") or []) for item in shots)}

    @staticmethod
    def _validate_reference_manifest(
        manifest: Any, *, label: str,
        resolve_reference: Callable[[str, str], dict[str, Any] | None] | None,
        reasons: list[str],
    ) -> None:
        if not isinstance(manifest, list):
            reasons.append(f"{label}缺少引用清单")
            return
        if len(manifest) > 12:
            reasons.append(f"{label}引用清单超过12项")
        seen_slots: set[tuple[str, int]] = set()
        for index, item in enumerate(manifest, start=1):
            prefix = f"{label}引用清单第{index}项"
            if not isinstance(item, dict):
                reasons.append(f"{prefix}必须是对象")
                continue
            fields = set(item)
            if fields != REFERENCE_MANIFEST_FIELDS:
                reasons.append(f"{prefix}字段不合法")
            kind = item.get("kind")
            if kind not in REFERENCE_MANIFEST_KINDS:
                reasons.append(f"{prefix}kind必须为image或video")
            slot = item.get("slot")
            if type(slot) is not int or not isinstance(kind, str) or not 1 <= slot <= REFERENCE_MANIFEST_KINDS.get(kind, 0):
                reasons.append(f"{prefix}slot超出允许范围")
            elif (kind, slot) in seen_slots:
                reasons.append(f"{prefix}slot重复")
            else:
                seen_slots.add((kind, slot))
            url = item.get("url")
            if not _is_sendable_url(url):
                reasons.append(f"{prefix}URL不可用")
            role = item.get("role")
            if not isinstance(role, str) or not role.strip():
                reasons.append(f"{prefix}role不能为空")
            for field in ("controls", "must_not_control"):
                value = item.get(field)
                if not isinstance(value, list) or not all(
                    isinstance(entry, str) and entry.strip() for entry in value
                ):
                    reasons.append(f"{prefix}{field}必须是字符串数组")
            if resolve_reference is not None and isinstance(kind, str) and _is_sendable_url(url):
                asset = resolve_reference(kind, str(url))
                if asset is None:
                    reasons.append(f"{prefix}URL不属于当前客户")
                elif asset.get("status") != "ready":
                    reasons.append(f"{prefix}引用资产状态不可用")
                elif asset.get("media_type") != kind:
                    reasons.append(f"{prefix}引用资产类型不匹配")
                elif asset.get("storage_uri") != url:
                    reasons.append(f"{prefix}URL不是已入库的可用地址")


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


def _is_sendable_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        return False
    parsed = urlsplit(value.strip())
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )
