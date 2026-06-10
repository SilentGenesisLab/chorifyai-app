"""Storage upload.

Aliyun OSS is used in cloud mode. In desktop/local mode, set
OSS_PROVIDER=local so files are written under LOCAL_STORAGE_ROOT and served by
the FastAPI app.
"""
import oss2

from app.core.config import settings
from app.services.local_storage import delete_keys, local_url, write_object


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
    if settings.oss_provider == "local":
        return local_url(key)
    base = (
        settings.aliyun_oss_public_base_url
        or f"https://{settings.aliyun_oss_bucket}.{settings.aliyun_oss_endpoint}"
    )
    return f"{base.rstrip('/')}/{key}"


def put_object(key: str, data: bytes, content_type: str | None = None) -> str:
    if settings.oss_provider == "local":
        return write_object(key, data)[0]
    if settings.oss_provider != "aliyun":
        return public_url(key)  # mock
    headers = {"Content-Type": content_type} if content_type else None
    _bucket().put_object(key, data, headers=headers)
    return public_url(key)


def delete_objects(keys: list[str]) -> list[str]:
    """Delete one or more objects from OSS. Best-effort: returns the keys that
    were issued for deletion. No-op (returns []) when not using real OSS."""
    keys = [k for k in keys if k]
    if not keys:
        return []
    if settings.oss_provider == "local":
        return delete_keys(keys)
    if settings.oss_provider != "aliyun":
        return []
    bucket = _bucket()
    # batch_delete_objects handles up to 1000 keys per call.
    for i in range(0, len(keys), 1000):
        bucket.batch_delete_objects(keys[i : i + 1000])
    return keys
