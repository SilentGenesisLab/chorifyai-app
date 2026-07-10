from datetime import datetime, timedelta, timezone

from app.insights import calculate_metrics


def test_download_and_quick_regenerate_signals():
    now = datetime.now(timezone.utc)
    rows = [
        {"ts": now.isoformat(), "action": "generate", "job_id": "a", "client_id": "c", "preset_id": "pain", "error_code": None, "result_url": "https://cdn/x"},
        {"ts": (now + timedelta(seconds=20)).isoformat(), "action": "download", "job_id": "a", "client_id": "c", "preset_id": "pain"},
        {"ts": now.isoformat(), "action": "generate", "job_id": "b", "client_id": "c", "preset_id": "pain", "error_code": None, "result_url": "https://cdn/x"},
        {"ts": (now + timedelta(seconds=30)).isoformat(), "action": "regenerate", "job_id": "b", "client_id": "c", "preset_id": "pain"},
        {"ts": now.isoformat(), "action": "generate", "job_id": "c", "client_id": "c", "preset_id": "pain", "error_code": None, "result_url": "https://cdn/x"},
    ]
    metric = calculate_metrics(rows)[0]
    assert (metric.generated, metric.downloaded, metric.quick_regenerated, metric.abandoned) == (3, 1, 1, 1)
    assert metric.download_rate == 1 / 3
