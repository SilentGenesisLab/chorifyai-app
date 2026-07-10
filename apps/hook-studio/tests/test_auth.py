from pathlib import Path

import pytest

from app.auth import AccessCodeStore, AuthError, SessionSigner
from app.models import Role


def _codes(path: Path):
    path.write_text("""codes:
  - id: client-one
    code: secret-123
    client_name: 客户甲
    role: client
    daily_video_limit: 20
    enabled: true
  - id: client-off
    code: secret-off
    client_name: 客户乙
    role: client
    enabled: false
""", encoding="utf-8")


def test_authenticate_returns_stable_id_not_real_code(tmp_path):
    path = tmp_path / "codes.yaml"
    _codes(path)
    principal = AccessCodeStore(path).authenticate("secret-123")
    assert principal.code_id == "client-one"
    assert principal.role is Role.CLIENT
    assert "secret-123" not in principal.model_dump_json()


def test_disabled_and_unknown_codes_are_rejected(tmp_path):
    path = tmp_path / "codes.yaml"
    _codes(path)
    store = AccessCodeStore(path)
    with pytest.raises(AuthError) as disabled:
        store.authenticate("secret-off")
    assert disabled.value.code == "CODE_DISABLED"
    with pytest.raises(AuthError) as unknown:
        store.authenticate("wrong")
    assert unknown.value.code == "AUTH_REQUIRED"
    with pytest.raises(AuthError) as disabled_id:
        store.get_principal("client-off")
    assert disabled_id.value.code == "CODE_DISABLED"


def test_session_signature_and_expiry(tmp_path):
    path = tmp_path / "codes.yaml"
    _codes(path)
    principal = AccessCodeStore(path).authenticate("secret-123")
    signer = SessionSigner("x" * 32, ttl_seconds=60)
    token, _ = signer.issue(principal, now=100)
    assert signer.verify(token, now=159).principal.code_id == "client-one"
    with pytest.raises(AuthError):
        signer.verify(token + "x", now=110)
    with pytest.raises(AuthError, match="过期"):
        signer.verify(token, now=160)
