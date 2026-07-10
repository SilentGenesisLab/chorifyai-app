from __future__ import annotations

from typing import Any


ANALYSIS_PROMPT = """请把参考视频逆向分析成JSON对象，字段必须包含：summary、hook、shots、audio、captions、transferable_patterns、do_not_copy。shots中每项包含start_ms、end_ms、purpose、visual、action、camera、sound。只记录可见或可听证据；不确定项写unknown。不要复制原人物身份、品牌、字幕、音乐或受保护表达。"""


class ReferenceAnalysisService:
    def __init__(self, provider: Any):
        self.provider = provider

    async def analyze(self, video_url: str, *, request_id: str, goal: str = "") -> dict[str, Any]:
        probe = await self.provider.probe_media(video_url, request_id=f"{request_id}:probe")
        duration = float(probe.get("duration") or (probe.get("format") or {}).get("duration") or 0)
        offsets = sorted({max(0.5, min(30.0, duration * fraction)) for fraction in (0.15, 0.35, 0.55, 0.75, 0.95)}, reverse=True)
        frames = []
        for index, offset in enumerate(offsets[:5]):
            try:
                frame = await self.provider.extract_frame(video_url, offset_from_end=offset, filename=f"analysis-{index + 1}.jpg", request_id=f"{request_id}:frame:{index}")
                if frame.result_url:
                    frames.append(frame.result_url)
            except Exception:
                continue
        analysis = await self.provider.understand(text=f"{ANALYSIS_PROMPT}\n分析目标：{goal or '复刻结构与生产方法'}", image_urls=frames, video_urls=[video_url], request_id=f"{request_id}:understand")
        return {"probe": probe, "frames": frames, "analysis": analysis, "provider": "kernel-understand"}
