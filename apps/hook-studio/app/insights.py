from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PresetMetric:
    client_id: str
    preset_id: str
    generated: int
    downloaded: int
    quick_regenerated: int
    abandoned: int

    @property
    def download_rate(self) -> float:
        return self.downloaded / self.generated if self.generated else 0.0


def calculate_metrics(rows: list[dict[str, Any]]) -> list[PresetMetric]:
    jobs: dict[str, dict[str, Any]] = {}
    grouped: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"generated": 0, "downloaded": 0, "quick_regenerated": 0, "abandoned": 0})
    for row in sorted(rows, key=lambda item: str(item["ts"])):
        action = row["action"]
        if action == "generate" and not row.get("error_code") and row.get("result_url") and row["job_id"] not in jobs:
            jobs[row["job_id"]] = row
            grouped[(row["client_id"], row["preset_id"])]["generated"] += 1
        elif row["job_id"] in jobs and action == "download":
            origin = jobs[row["job_id"]]
            grouped[(origin["client_id"], origin["preset_id"])]["downloaded"] += 1
        elif row["job_id"] in jobs and action == "regenerate":
            origin = jobs[row["job_id"]]
            start = datetime.fromisoformat(str(origin["ts"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
            if (end - start).total_seconds() <= 60:
                grouped[(origin["client_id"], origin["preset_id"])]["quick_regenerated"] += 1
    acted = {(row["job_id"]) for row in rows if row["action"] in {"download", "regenerate", "preview", "delete"}}
    for job_id, origin in jobs.items():
        if job_id not in acted:
            grouped[(origin["client_id"], origin["preset_id"])]["abandoned"] += 1
    return [PresetMetric(client, preset, **counts) for (client, preset), counts in grouped.items()]


class InsightsService:
    def __init__(self, db: Any):
        self.db = db

    def event_rows(self, *, since: datetime | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM events"
        params: tuple[Any, ...] = ()
        if since:
            query += " WHERE ts>=?"
            params = (since.isoformat(),)
        query += " ORDER BY ts"
        with self.db.transaction() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def metrics(self, *, days: int = 7) -> list[PresetMetric]:
        return calculate_metrics(self.event_rows(since=datetime.now(timezone.utc) - timedelta(days=days)))

    def preset_order(self) -> list[str]:
        aggregate: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        for item in self.metrics():
            generated, downloaded = aggregate[item.preset_id]
            aggregate[item.preset_id] = (generated + item.generated, downloaded + item.downloaded)
        return sorted(aggregate, key=lambda preset: (aggregate[preset][1] / aggregate[preset][0] if aggregate[preset][0] else 0, aggregate[preset][0]), reverse=True)

    def render_hook_insights(self, *, report_date: date | None = None) -> str:
        report_date = report_date or date.today()
        metrics = self.metrics()
        global_rows: dict[str, list[PresetMetric]] = defaultdict(list)
        for item in metrics:
            global_rows[item.preset_id].append(item)
        ranking = []
        for preset, items in global_rows.items():
            generated = sum(item.generated for item in items)
            downloaded = sum(item.downloaded for item in items)
            ranking.append((downloaded / generated if generated else 0, preset, generated, downloaded))
        ranking.sort(reverse=True)
        lines = [f"# HOOK_INSIGHTS_{report_date.isoformat()}", "", "## 预设下载率排行", ""]
        if not ranking:
            lines.append("本周期暂无有效生成数据。")
        else:
            lines.extend(f"{index}. `{preset}`：{rate:.1%}（下载 {downloaded} / 生成 {generated}）" for index, (rate, preset, generated, downloaded) in enumerate(ranking, 1))
        lines.extend(["", "## 典型高分产物", ""])
        with self.db.transaction() as conn:
            urls = conn.execute("SELECT DISTINCT result_url,preset_id FROM events WHERE action='download' AND result_url IS NOT NULL ORDER BY ts DESC LIMIT 20").fetchall()
        lines.extend(f"- `{row['preset_id']}`：{row['result_url']}" for row in urls)
        if not urls:
            lines.append("本周期暂无下载产物。")
        lines.extend(["", "## 信号说明", "", "下载为强正票；60秒内重生成为弱负票；生成后无预览、下载、重生成或删除动作为弃票。", ""])
        return "\n".join(lines)

    def write_hook_insights(self, directory: str | Path, *, report_date: date | None = None) -> Path:
        report_date = report_date or date.today()
        target = Path(directory) / f"HOOK_INSIGHTS_{report_date.isoformat()}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render_hook_insights(report_date=report_date), encoding="utf-8")
        return target

    def render_digest(self) -> str:
        metrics = self.metrics()
        generated = sum(item.generated for item in metrics)
        downloaded = sum(item.downloaded for item in metrics)
        quick_negative = sum(item.quick_regenerated for item in metrics)
        abandoned = sum(item.abandoned for item in metrics)
        top = self.preset_order()[:3]
        return "\n".join([
            "# WEEKLY_DEMO_DIGEST", "", f"1. 本周生成 {generated} 条。", f"2. 本周下载 {downloaded} 条。",
            f"3. 整体下载率 {(downloaded / generated if generated else 0):.1%}。", f"4. 60秒内重生成 {quick_negative} 次。",
            f"5. 弃票 {abandoned} 条。", f"6. 当前前三预设：{'、'.join(top) if top else '暂无数据'}。",
            "7. 图片和视频队列继续独立观测。", "8. 视频成功仅统计通过音轨、时长和比例安检的成片。",
            "9. 灰度模板只在下载率胜出后转正。", "10. 下周优先复核弱负票最多的预设。", "",
        ])
