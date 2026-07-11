from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ShotPlan:
    ordinal: int
    duration: int
    title: str
    purpose: str
    visual: str
    action: str
    camera: str
    sound: str
    prompt: str
    story_function: str = ""
    shot_size: str = "近景"
    camera_angle: str = "平视"
    camera_height: str = "主体中心高度"
    lens_feel: str = "35mm真实摄影感"
    composition: str = "主体位于9:16安全区中央"
    action_start: str = ""
    action_trigger: str = ""
    action_result: str = ""
    camera_move: str = ""
    transition: str = "按动作完成点切镜"
    stable_truth: tuple[str, ...] = ("产品结构", "主体身份", "空间方向")
    may_vary: tuple[str, ...] = ("手部微动作", "环境细节")
    reference_manifest: tuple[dict[str, Any], ...] = ()
    first_failure_cue: str = "主体结构、动作因果或空间方向首先发生漂移"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def split_duration(total_seconds: int, *, minimum: int = 4, maximum: int = 15) -> list[int]:
    if total_seconds < minimum:
        raise ValueError(f"视频总时长不能少于{minimum}秒")
    count = math.ceil(total_seconds / maximum)
    if total_seconds < count * minimum:
        raise ValueError("视频时长无法拆成合法分段")
    base, remainder = divmod(total_seconds, count)
    result = [base + (1 if index < remainder else 0) for index in range(count)]
    if any(value < minimum or value > maximum for value in result) or sum(result) != total_seconds:
        raise ValueError("视频分段计算失败")
    return result


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if isinstance(value.get("output"), dict):
            return value["output"]
        return value
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if "```" in text:
        text = text.split("```", 2)[1].removeprefix("json").strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def normalize_plan(raw: Any, *, brief: str, durations: list[int], tool: str) -> list[ShotPlan]:
    payload = _json_object(raw)
    source = payload.get("shots") if isinstance(payload.get("shots"), list) else []
    plans: list[ShotPlan] = []
    for index, duration in enumerate(durations):
        item = source[index] if index < len(source) and isinstance(source[index], dict) else {}
        title = str(item.get("title") or f"镜头 {index + 1}")
        purpose = str(item.get("purpose") or ("建立钩子" if index == 0 else "推进证明与结果"))
        visual = str(item.get("visual") or brief)
        action = str(item.get("action") or "主体执行一个清晰动作，随后展示可验证结果")
        camera = str(item.get("camera") or "9:16真实手持近景，单一连续运镜")
        sound = str(item.get("sound") or "保留与动作同步的环境音和动作音")
        prompt = str(item.get("prompt") or f"{camera}。{visual}。触发后，{action}。{sound}。无字幕、无水印、无竞品标识。")
        plans.append(ShotPlan(
            index + 1, duration, title, purpose, visual, action, camera, sound, prompt,
            story_function=str(item.get("story_function") or purpose),
            shot_size=str(item.get("shot_size") or "近景"),
            camera_angle=str(item.get("camera_angle") or "平视"),
            camera_height=str(item.get("camera_height") or "主体中心高度"),
            lens_feel=str(item.get("lens_feel") or "35mm真实摄影感"),
            composition=str(item.get("composition") or "主体位于9:16安全区中央，前中后景关系清楚"),
            action_start=str(item.get("action_start") or f"动作开始前，{visual}"),
            action_trigger=str(item.get("action_trigger") or action),
            action_result=str(item.get("action_result") or "动作完成，结果清楚且可验证"),
            camera_move=str(item.get("camera_move") or camera),
            transition=str(item.get("transition") or "按动作完成点切镜"),
            stable_truth=tuple(item.get("stable_truth") or ("产品结构", "主体身份", "空间方向")),
            may_vary=tuple(item.get("may_vary") or ("手部微动作", "环境细节")),
            reference_manifest=tuple(item.get("reference_manifest") or ()),
            first_failure_cue=str(item.get("first_failure_cue") or "主体结构、动作因果或空间方向首先发生漂移"),
        ))
    return plans


def planning_prompt(*, brief: str, tool: str, durations: list[int], context: str = "") -> str:
    return f"""你是美区TikTok商业短视频导演。请只返回JSON对象，不要Markdown。
任务类型：{tool}
用户目标：{brief}
总镜头数：{len(durations)}
每镜头时长：{durations}
素材解析摘要：{context[:6000]}
   输出结构：{{"title":"项目标题","summary":"生产策略","shots":[{{"title":"镜头标题","story_function":"本镜叙事功能","visual":"完整可见画面","shot_size":"景别","camera_angle":"机位角度","camera_height":"机位高度","lens_feel":"镜头质感","composition":"前中后景构图","action_start":"动作起点","action_trigger":"触发与动作变化","action_result":"动作结果","camera_move":"单一运镜","sound":"声音意图","transition":"转场点","stable_truth":["必须稳定的事实"],"may_vary":["允许变化"],"first_failure_cue":"最先失败征兆","prompt":"服务端生成提示词"}}]}}
   硬约束：shots数量必须等于{len(durations)}；每镜头只做一个主要动作；动作起点、变化和结果都必须可见；描述人物、产品、场景、光线、构图、景别、机位、运镜、声音和转场；9:16；不得复制参考视频的原人物、品牌、字幕、音乐或受保护表达。"""
