from __future__ import annotations

import pytest

from app.url_policy import is_sendable_media_url


@pytest.mark.parametrize("value", [
    "file:///C:/legacy.png",
    "https://user:pass@example.com/legacy.png",
    "https://example.com/legacy.png#fragment",
    "https://example.com/" + "a" * 4096,
    "https:///missing-host.png",
    "   ",
])
def test_media_url_policy_rejects_values_that_must_not_cross_kernel(value):
    assert not is_sendable_media_url(value)


@pytest.mark.parametrize("value", [
    "https://cdn.example/legacy.png",
    "http://127.0.0.1:9000/reference.mp4?version=2",
])
def test_media_url_policy_accepts_bounded_http_sources(value):
    assert is_sendable_media_url(value)
