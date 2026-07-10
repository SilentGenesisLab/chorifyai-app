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


def test_batch_assets_cannot_exceed_one_hundred_percent_download_rate():
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for index in range(3):
        url = f"https://cdn/{index}.mp4"
        rows.append({"ts": now, "action": "generate", "job_id": "batch", "client_id": "c", "preset_id": "batch", "error_code": None, "result_url": url})
        rows.append({"ts": now, "action": "download", "job_id": "batch", "client_id": "c", "preset_id": "batch", "result_url": url})
        rows.append({"ts": now, "action": "download", "job_id": "batch", "client_id": "c", "preset_id": "batch", "result_url": url})
    metric = calculate_metrics(rows)[0]
    assert (metric.generated, metric.downloaded, metric.abandoned) == (3, 3, 0)
    assert metric.download_rate == 1
