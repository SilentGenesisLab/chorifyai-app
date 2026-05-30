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
