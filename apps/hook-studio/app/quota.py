from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.db import Database
from app.models import UsageSnapshot

CN_TZ = timezone(timedelta(hours=8))


class QuotaExceeded(Exception):
    code = "QUOTA_EXHAUSTED"

    def __init__(self, message: str, snapshot: UsageSnapshot):
        self.snapshot = snapshot
        super().__init__(message)


def china_day(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(CN_TZ).date().isoformat()


def next_reset_at(now: datetime | None = None) -> datetime:
    value = (now or datetime.now(timezone.utc)).astimezone(CN_TZ)
    return datetime.combine(value.date() + timedelta(days=1), datetime.min.time(), CN_TZ)


class QuotaService:
    def __init__(self, db: Database, global_limit: int):
        self.db = db
        self.global_limit = global_limit

    @staticmethod
    def _ensure_row(conn, day: str, client_id: str, now_iso: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO daily_usage(day_cn, client_id, updated_at) VALUES (?, ?, ?)",
            (day, client_id, now_iso),
        )

    def _snapshot(self, conn, day: str, client_id: str, client_limit: int) -> UsageSnapshot:
        row = conn.execute(
            "SELECT video_reserved, video_succeeded, video_failed FROM daily_usage WHERE day_cn=? AND client_id=?",
            (day, client_id),
        ).fetchone()
        totals = conn.execute(
            "SELECT COALESCE(SUM(video_reserved),0) reserved, COALESCE(SUM(video_succeeded),0) succeeded FROM daily_usage WHERE day_cn=?",
            (day,),
        ).fetchone()
        return UsageSnapshot(
            day_cn=day, client_id=client_id,
            client_reserved=row["video_reserved"], client_succeeded=row["video_succeeded"],
            client_failed=row["video_failed"], global_reserved=totals["reserved"],
            global_succeeded=totals["succeeded"], client_limit=client_limit,
            global_limit=self.global_limit,
        )

    def reserve_video(self, client_id: str, client_limit: int, *, now: datetime | None = None) -> UsageSnapshot:
        day = china_day(now)
        now_iso = (now or datetime.now(timezone.utc)).isoformat()
        with self.db.transaction(immediate=True) as conn:
            self._ensure_row(conn, day, client_id, now_iso)
            snapshot = self._snapshot(conn, day, client_id, client_limit)
            if snapshot.client_reserved + snapshot.client_succeeded >= client_limit:
                raise QuotaExceeded("该访问码今日视频额度已用完", snapshot)
            if snapshot.global_reserved + snapshot.global_succeeded >= self.global_limit:
                raise QuotaExceeded("今日全站视频额度已用完", snapshot)
            conn.execute(
                "UPDATE daily_usage SET video_reserved=video_reserved+1, updated_at=? WHERE day_cn=? AND client_id=?",
                (now_iso, day, client_id),
            )
            return self._snapshot(conn, day, client_id, client_limit)

    def mark_succeeded(
        self, client_id: str, client_limit: int, *, now: datetime | None = None,
        reservation_day: str | None = None,
    ) -> UsageSnapshot:
        return self._finish(
            client_id, client_limit, succeeded=True, now=now, reservation_day=reservation_day,
        )

    def release_failed(
        self, client_id: str, client_limit: int, *, now: datetime | None = None,
        reservation_day: str | None = None,
    ) -> UsageSnapshot:
        return self._finish(
            client_id, client_limit, succeeded=False, now=now, reservation_day=reservation_day,
        )

    def _finish(
        self, client_id: str, client_limit: int, *, succeeded: bool,
        now: datetime | None, reservation_day: str | None,
    ) -> UsageSnapshot:
        day = reservation_day or china_day(now)
        date.fromisoformat(day)
        now_iso = (now or datetime.now(timezone.utc)).isoformat()
        with self.db.transaction(immediate=True) as conn:
            self._ensure_row(conn, day, client_id, now_iso)
            row = conn.execute(
                "SELECT video_reserved FROM daily_usage WHERE day_cn=? AND client_id=?", (day, client_id)
            ).fetchone()
            if row["video_reserved"] <= 0:
                raise ValueError("no reserved video quota to finish")
            target = "video_succeeded" if succeeded else "video_failed"
            conn.execute(
                f"UPDATE daily_usage SET video_reserved=video_reserved-1, {target}={target}+1, updated_at=? WHERE day_cn=? AND client_id=?",
                (now_iso, day, client_id),
            )
            return self._snapshot(conn, day, client_id, client_limit)

    def snapshot(self, client_id: str, client_limit: int, *, now: datetime | None = None) -> UsageSnapshot:
        day = china_day(now)
        with self.db.transaction() as conn:
            self._ensure_row(conn, day, client_id, datetime.now(timezone.utc).isoformat())
            return self._snapshot(conn, day, client_id, client_limit)
