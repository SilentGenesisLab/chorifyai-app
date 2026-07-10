from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.models import AccessCodeRecord, Principal, Role


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True, slots=True)
class Session:
    principal: Principal
    expires_at: int


class AccessCodeStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> list[AccessCodeRecord]:
        if not self.path.exists():
            raise RuntimeError(f"access code file does not exist: {self.path}")
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        records = [AccessCodeRecord.model_validate(item) for item in raw.get("codes", [])]
        if len({item.id for item in records}) != len(records):
            raise RuntimeError("duplicate access code id")
        if len({item.code for item in records}) != len(records):
            raise RuntimeError("duplicate access code value")
        return records

    def authenticate(self, supplied_code: str) -> Principal:
        disabled_match = False
        for record in self.load():
            if hmac.compare_digest(record.code.encode(), supplied_code.encode()):
                if not record.enabled:
                    disabled_match = True
                    break
                return Principal(
                    code_id=record.id,
                    client_name=record.client_name,
                    role=record.role,
                    daily_video_limit=record.daily_video_limit,
                )
        if disabled_match:
            raise AuthError("CODE_DISABLED", "访问码已停用，请联系管理员")
        raise AuthError("AUTH_REQUIRED", "访问码无效")

    def get_principal(self, code_id: str) -> Principal:
        """Reload authorization state so disabling a code revokes active sessions."""
        for record in self.load():
            if hmac.compare_digest(record.id.encode(), code_id.encode()):
                if not record.enabled:
                    raise AuthError("CODE_DISABLED", "访问码已停用，请联系管理员")
                return Principal(
                    code_id=record.id,
                    client_name=record.client_name,
                    role=record.role,
                    daily_video_limit=record.daily_video_limit,
                )
        raise AuthError("AUTH_REQUIRED", "访问码不存在，请重新登录")


class SessionSigner:
    def __init__(self, secret: str, ttl_seconds: int):
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def issue(self, principal: Principal, *, now: int | None = None) -> tuple[str, int]:
        issued_at = int(time.time() if now is None else now)
        expires_at = issued_at + self.ttl_seconds
        payload = _b64encode(json.dumps({
            "sub": principal.code_id,
            "name": principal.client_name,
            "role": principal.role.value,
            "limit": principal.daily_video_limit,
            "iat": issued_at,
            "exp": expires_at,
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        signature = _b64encode(hmac.new(self.secret, payload.encode(), hashlib.sha256).digest())
        return f"{payload}.{signature}", expires_at

    def verify(self, token: str, *, now: int | None = None) -> Session:
        try:
            payload, signature = token.split(".", 1)
            expected = _b64encode(hmac.new(self.secret, payload.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature mismatch")
            data = json.loads(_b64decode(payload))
            current = int(time.time() if now is None else now)
            if current >= int(data["exp"]):
                raise AuthError("AUTH_REQUIRED", "登录已过期，请重新输入访问码")
            principal = Principal(
                code_id=data["sub"], client_name=data["name"],
                role=Role(data["role"]), daily_video_limit=int(data["limit"]),
            )
            return Session(principal=principal, expires_at=int(data["exp"]))
        except AuthError:
            raise
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AuthError("AUTH_REQUIRED", "登录凭证无效") from exc
