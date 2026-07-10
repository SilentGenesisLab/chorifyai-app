from datetime import datetime, timezone

import pytest

from app.db import Database
from app.quota import QuotaExceeded, QuotaService, china_day, next_reset_at


def _service(tmp_path, limit=2):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    return QuotaService(db, limit)


def test_china_day_and_reset_boundary():
    before = datetime(2026, 7, 9, 15, 59, tzinfo=timezone.utc)
    after = datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc)
    assert china_day(before) == "2026-07-09"
    assert china_day(after) == "2026-07-10"
    assert next_reset_at(before).isoformat() == "2026-07-10T00:00:00+08:00"


def test_reserve_success_and_failure_release(tmp_path):
    service = _service(tmp_path, limit=3)
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    assert service.reserve_video("client-a", 2, now=now).client_reserved == 1
    done = service.mark_succeeded("client-a", 2, now=now)
    assert done.client_reserved == 0 and done.client_succeeded == 1
    service.reserve_video("client-a", 2, now=now)
    released = service.release_failed("client-a", 2, now=now)
    assert released.client_failed == 1 and released.client_reserved == 0
    assert released.client_succeeded == 1


def test_client_and_global_limits_are_server_enforced(tmp_path):
    service = _service(tmp_path, limit=2)
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    service.reserve_video("client-a", 1, now=now)
    with pytest.raises(QuotaExceeded, match="访问码"):
        service.reserve_video("client-a", 1, now=now)
    service.reserve_video("client-b", 2, now=now)
    with pytest.raises(QuotaExceeded, match="全站"):
        service.reserve_video("client-c", 2, now=now)


def test_new_china_day_has_fresh_quota(tmp_path):
    service = _service(tmp_path, limit=1)
    service.reserve_video("client-a", 1, now=datetime(2026, 7, 9, 15, 59, tzinfo=timezone.utc))
    snapshot = service.reserve_video("client-a", 1, now=datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc))
    assert snapshot.day_cn == "2026-07-10"


def test_cross_midnight_completion_uses_reservation_day(tmp_path):
    service = _service(tmp_path, limit=1)
    reserved = service.reserve_video(
        "client-a", 1, now=datetime(2026, 7, 9, 15, 59, tzinfo=timezone.utc),
    )
    finished = service.mark_succeeded(
        "client-a", 1, now=datetime(2026, 7, 9, 16, 1, tzinfo=timezone.utc),
        reservation_day=reserved.day_cn,
    )
    assert finished.day_cn == "2026-07-09"
    assert finished.client_reserved == 0 and finished.client_succeeded == 1
