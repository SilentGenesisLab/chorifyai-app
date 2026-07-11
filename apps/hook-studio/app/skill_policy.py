from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PolicyCheck:
    id: str
    status: str
    hard: bool = True
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyTrace:
    policy_pack: str
    version: str
    checks: list[PolicyCheck]
    slot_manifest: list[dict[str, Any]]

    @property
    def passed(self) -> bool:
        return not any(item.hard and item.status == "fail" for item in self.checks)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["passed"] = self.passed
        return value


class SkillGateBlocked(ValueError):
    code = "SKILL_GATE_BLOCKED"

    def __init__(self, trace: PolicyTrace):
        self.trace = trace
        failed = [item.message for item in trace.checks if item.status == "fail"]
        super().__init__("；".join(failed) or "视频生成前检查未通过")


class VideoSkillPolicy:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    @classmethod
    def from_file(cls, path: str | Path) -> "VideoSkillPolicy":
        text = Path(path).read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise RuntimeError("policy must be JSON-compatible YAML when PyYAML is unavailable") from exc
            data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("skill policy root must be an object")
        return cls(data)

    def evaluate(
        self,
        *,
        prompt: str,
        duration: int,
        ratio: str,
        reference_urls: list[str] | None = None,
        slot_manifest: list[dict[str, Any]] | None = None,
    ) -> PolicyTrace:
        refs = list(reference_urls or [])
        manifest = list(slot_manifest or [])
        checks: list[PolicyCheck] = []

        expected_slots = list(range(1, len(refs) + 1))
        actual_slots = [item.get("slot") for item in manifest]
        slot_ok = len(refs) <= int(self.config.get("max_reference_images", 4)) and ((not refs and not manifest) or actual_slots == expected_slots)
        checks.append(PolicyCheck("slot-order", "pass" if slot_ok else "fail", message="参考图槽位必须从图片1连续排列", evidence={"actual": actual_slots, "expected": expected_slots}))

        roles_ok = (not refs and not manifest) or (
            len(manifest) == len(refs)
            and all(item.get("url") == refs[index] and str(item.get("role", "")).strip() for index, item in enumerate(manifest))
        )
        checks.append(PolicyCheck("reference-role", "pass" if roles_ok else "fail", message="每张参考图必须绑定唯一且明确的角色", evidence={"reference_count": len(refs), "manifest_count": len(manifest)}))

        action_terms = self.config.get("required_action_terms", [])
        action_ok = len(prompt.strip()) >= int(self.config.get("prompt_min_length", 1)) and any(term in prompt for term in action_terms)
        checks.append(PolicyCheck("action-causality", "pass" if action_ok else "fail", message="请写清主体动作及动作先后关系"))

        duration_ok = duration in self.config.get("duration_seconds", list(range(4, 16))) and ratio == self.config.get("ratio", "9:16")
        checks.append(PolicyCheck("duration-ratio", "pass" if duration_ok else "fail", message="单镜视频仅支持4-15秒、9:16竖屏", evidence={"duration": duration, "ratio": ratio}))

        audio_terms = self.config.get("required_audio_terms", [])
        audio_ok = all(term in prompt for term in audio_terms)
        checks.append(PolicyCheck("native-audio-intent", "pass" if audio_ok else "fail", message="提示词必须同时要求原生环境音和动作音"))

        prohibited = []
        for term in self.config.get("prohibited_terms", []):
            for match in re.finditer(re.escape(term), prompt, re.IGNORECASE):
                clause_start = max(prompt.rfind(mark, 0, match.start()) for mark in ("。", "；", ";", "！", "!", "？", "?"))
                prefix = prompt[clause_start + 1:match.start()]
                if not any(negation in prefix for negation in ("不出现", "不得有", "不要", "无", "禁止")):
                    prohibited.append(term)
                    break
        checks.append(PolicyCheck("privacy-prohibited-elements", "pass" if not prohibited else "fail", message="提示词含禁止内容，请删除后重试", evidence={"matched_terms": prohibited}))

        return PolicyTrace(
            policy_pack=str(self.config.get("policy_pack", "hook-video-reliability")),
            version=str(self.config.get("version", "0")),
            checks=checks,
            slot_manifest=manifest,
        )

    def require(self, **kwargs: Any) -> PolicyTrace:
        trace = self.evaluate(**kwargs)
        if not trace.passed:
            raise SkillGateBlocked(trace)
        return trace
