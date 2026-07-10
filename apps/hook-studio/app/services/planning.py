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
        plans.append(ShotPlan(index + 1, duration, title, purpose, visual, action, camera, sound, prompt))
    return plans


def planning_prompt(*, brief: str, tool: str, durations: list[int], context: str = "") -> str:
    return f"""你是美区TikTok商业短视频导演。请只返回JSON对象，不要Markdown。
任务类型：{tool}
用户目标：{brief}
总镜头数：{len(durations)}
每镜头时长：{durations}
素材解析摘要：{context[:6000]}
输出结构：{{"title":"项目标题","summary":"生产策略","shots":[{{"title":"镜头标题","purpose":"镜头功能","visual":"可见画面","action":"触发->动作->结果","camera":"景别和单一运镜","sound":"声音意图","prompt":"可直接用于Seedance的中文提示词"}}]}}
硬约束：shots数量必须等于{len(durations)}；每镜头只做一个主要动作；9:16；产品、人物、场景和动作因果可拍；不得复制参考视频的原人物、品牌、字幕、音乐或受保护表达。"""

