import json
import os
import shutil
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from app.core.config import settings

_ROOT_OVERRIDE: Path | None = None


def _default_config_path() -> Path:
    raw = settings.local_storage_config or os.environ.get("LOCAL_STORAGE_CONFIG")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".chorifyai" / "local-storage.json"


def _default_root() -> Path:
    raw = settings.local_storage_root or os.environ.get("LOCAL_STORAGE_ROOT")
    if raw:
        return Path(raw).expanduser()
    try:
        payload = json.loads(_default_config_path().read_text(encoding="utf-8"))
        if payload.get("root"):
            return Path(str(payload["root"])).expanduser()
    except Exception:
        pass
    return Path.home() / "Documents" / "ChorifyAI" / "workspace"


def storage_root() -> Path:
    root = (_ROOT_OVERRIDE or _default_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def set_storage_root(path: str) -> Path:
    global _ROOT_OVERRIDE
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _ROOT_OVERRIDE = root
    config = _default_config_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"root": str(root)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def safe_path_for_key(key: str) -> Path:
    normalized = unquote(key).replace("\\", "/").lstrip("/")
    if ".." in Path(normalized).parts:
        raise ValueError("Invalid storage key")
    path = (storage_root() / normalized).resolve()
    root = storage_root()
    if path != root and root not in path.parents:
        raise ValueError("Storage key escapes local root")
    return path


def local_url(key: str) -> str:
    return "/api/local-files/" + quote(key.replace("\\", "/").lstrip("/"), safe="/")


def write_object(key: str, data: bytes) -> tuple[str, str]:
    path = safe_path_for_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return local_url(key), str(path)


def object_path(key: str) -> str | None:
    try:
        path = safe_path_for_key(key)
    except ValueError:
        return None
    return str(path) if path.exists() else None


def delete_keys(keys: list[str]) -> list[str]:
    deleted: list[str] = []
    for key in keys:
        if not key:
            continue
        try:
            path = safe_path_for_key(key)
            if path.exists():
                path.unlink()
                deleted.append(key)
        except Exception:
            continue
    return deleted


def maybe_local_path(url_or_path: str) -> str | None:
    value = (url_or_path or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    path_part = parsed.path if parsed.scheme in {"http", "https"} else value
    marker = "/api/local-files/"
    if marker in path_part:
        key = path_part.split(marker, 1)[1]
        path = safe_path_for_key(key)
        return str(path) if path.exists() else None
    candidate = Path(value)
    if candidate.exists():
        return str(candidate.resolve())
    return None


def copy_or_download_to(url_or_path: str, dst: str, download_fn) -> str:
    local = maybe_local_path(url_or_path)
    if local:
        shutil.copyfile(local, dst)
        return dst
    return download_fn(url_or_path, dst)
