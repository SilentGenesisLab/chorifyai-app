"""Aliyun OSS upload (oss2). Real storage for product images / video / audio /
generic files. Set OSS_PROVIDER=mock to skip network and return fake URLs."""
import oss2

from app.core.config import settings


def _bucket() -> oss2.Bucket:
    auth = oss2.Auth(
        settings.aliyun_oss_access_key_id,
        settings.aliyun_oss_access_key_secret,
    )
    return oss2.Bucket(
        auth,
        f"https://{settings.aliyun_oss_endpoint}",
        settings.aliyun_oss_bucket,
    )


def public_url(key: str) -> str:
    base = (
        settings.aliyun_oss_public_base_url
        or f"https://{settings.aliyun_oss_bucket}.{settings.aliyun_oss_endpoint}"
    )
    return f"{base.rstrip('/')}/{key}"


def put_object(key: str, data: bytes, content_type: str | None = None) -> str:
    if settings.oss_provider != "aliyun":
        return public_url(key)  # mock
    headers = {"Content-Type": content_type} if content_type else None
    _bucket().put_object(key, data, headers=headers)
    return public_url(key)


def delete_objects(keys: list[str]) -> list[str]:
    """Delete one or more objects from OSS. Best-effort: returns the keys that
    were issued for deletion. No-op (returns []) when not using real OSS."""
    keys = [k for k in keys if k]
    if not keys or settings.oss_provider != "aliyun":
        return []
    bucket = _bucket()
    # batch_delete_objects handles up to 1000 keys per call.
    for i in range(0, len(keys), 1000):
        bucket.batch_delete_objects(keys[i : i + 1000])
    return keys
