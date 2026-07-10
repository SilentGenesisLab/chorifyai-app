from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.auth import AccessCodeStore, AuthError, SessionSigner
from app.models import LoginRequest, LoginResponse, Principal, Role
from app.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE_NAME = "hook_studio_session"


def get_settings() -> Settings:
    return Settings.from_env()


def get_store(settings: Settings = Depends(get_settings)) -> AccessCodeStore:
    return AccessCodeStore(settings.access_codes_file)


def get_signer(settings: Settings = Depends(get_settings)) -> SessionSigner:
    return SessionSigner(settings.session_secret, settings.session_ttl_seconds)


def _unauthorized(error: AuthError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error_code": error.code, "message": str(error)},
    )


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    response: Response,
    store: AccessCodeStore = Depends(get_store),
    signer: SessionSigner = Depends(get_signer),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    try:
        principal = store.authenticate(body.access_code)
    except AuthError as exc:
        raise _unauthorized(exc) from exc
    token, expires_at = signer.issue(principal)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds, path=settings.base_path,
    )
    return LoginResponse(principal=principal, expires_at=datetime.fromtimestamp(expires_at, timezone.utc))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, settings: Settings = Depends(get_settings)) -> Response:
    response.delete_cookie(COOKIE_NAME, path=settings.base_path)
    return response


def require_principal(
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    signer: SessionSigner = Depends(get_signer),
    store: AccessCodeStore = Depends(get_store),
) -> Principal:
    if not token:
        raise _unauthorized(AuthError("AUTH_REQUIRED", "请先输入访问码"))
    try:
        session = signer.verify(token)
        return store.get_principal(session.principal.code_id)
    except AuthError as exc:
        raise _unauthorized(exc) from exc


def require_admin(principal: Principal = Depends(require_principal)) -> Principal:
    if principal.role is not Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error_code": "AUTH_REQUIRED", "message": "需要管理员权限",
        })
    return principal


@router.get("/me", response_model=Principal)
def me(principal: Principal = Depends(require_principal)) -> Principal:
    return principal
