from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, studio
from app.auth import AccessCodeStore, AuthError, SessionSigner
from app.backup import BackupManager
from app.db import Database
from app.events import EventWriter
from app.insights import InsightsService
from app.providers.kernel import KernelProvider
from app.providers.fake import FakeKernelProvider
from app.qc import VideoPostflightQC
from app.quota import QuotaService
from app.queues import QueueManager
from app.services.generation import GenerationService, SQLiteJobRepository
from app.settings import Settings
from app.skill_policy import VideoSkillPolicy


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"


def _load_presets() -> list[dict]:
    data = yaml.safe_load((ROOT / "config" / "presets-v1.yaml").read_text(encoding="utf-8")) or {}
    return list(data.get("presets", []))


def _apply_persisted_settings(settings: Settings, db: Database) -> Settings:
    with db.transaction() as conn:
        rows = {row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT key,value FROM settings").fetchall()}
    changes = {}
    for key in ("global_video_daily_limit", "image_concurrency", "video_concurrency"):
        if key in rows:
            changes[key] = int(rows[key])
    return replace(settings, **changes) if changes else settings


class KernelBackupUploader:
    def __init__(self, provider: KernelProvider):
        self.provider = provider

    async def upload(self, archive: Path, key: str) -> str:
        return await self.provider.upload_blob(
            key, archive.read_bytes(), "application/gzip", stage="backup.upload", request_id=f"backup-{archive.stem}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path)
    db.initialize()
    settings = _apply_persisted_settings(settings, db)
    store = AccessCodeStore(settings.access_codes_file)
    store.load()
    provider = (
        FakeKernelProvider()
        if settings.provider_mode == "fake"
        else KernelProvider(settings.kernel_base_url, settings.kernel_bearer, timeout_seconds=70)
    )
    quota = QuotaService(db, settings.global_video_daily_limit)
    events = EventWriter(db, settings.events_path)
    repository = SQLiteJobRepository(db)
    policy = VideoSkillPolicy.from_file(ROOT / "config" / "skill-policy-v1.yaml")
    qc = VideoPostflightQC(provider.probe_media)
    generation = GenerationService(repository, provider, quota, events, policy, qc)
    queues = QueueManager(
        generation.process,
        image_concurrency=settings.image_concurrency,
        video_concurrency=settings.video_concurrency,
    )
    generation.bind_queues(queues)
    app.state.settings = settings
    app.state.db = db
    app.state.access_store = store
    app.state.session_signer = SessionSigner(settings.session_secret, settings.session_ttl_seconds)
    app.state.provider = provider
    app.state.quota = quota
    app.state.generation_service = generation
    app.state.queues = queues
    app.state.presets = _load_presets()
    app.state.backup = BackupManager(
        settings.database_path, settings.events_path, settings.data_dir / "backups",
        uploader=KernelBackupUploader(provider) if isinstance(provider, KernelProvider) else None,
    )
    app.state.insights = InsightsService(db)
    with db.transaction() as conn:
        backup_row = conn.execute("SELECT value FROM settings WHERE key='last_backup'").fetchone()
    app.state.backup_status = json.loads(backup_row["value"]) if backup_row else "尚未执行"
    await queues.start()
    app.state.recovered_jobs = await queues.recover(repository)
    try:
        yield
    finally:
        await queues.stop()


app = FastAPI(title="Hook Studio", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(auth.router)
app.include_router(studio.router)
app.include_router(admin.router)


@app.middleware("http")
async def security_and_auth(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    path = request.url.path
    public = path in {"/healthz", "/api/auth/login"} or not path.startswith("/api/")
    if not public:
        token = request.cookies.get(auth.COOKIE_NAME)
        if not token:
            return JSONResponse(
                {"detail": {"error_code": "AUTH_REQUIRED", "message": "请先输入访问码", "request_id": request_id}},
                status_code=401,
                headers={"X-Request-ID": request_id},
            )
        try:
            session = request.app.state.session_signer.verify(token)
            request.state.principal = request.app.state.access_store.get_principal(session.principal.code_id)
        except AuthError as exc:
            return JSONResponse(
                {"detail": {"error_code": exc.code, "message": str(exc), "request_id": request_id}},
                status_code=401,
                headers={"X-Request-ID": request_id},
            )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    return JSONResponse(
        {"detail": {"error_code": "INTERNAL_ERROR", "message": "服务暂时不可用，请稍后重试", "request_id": request_id}},
        status_code=500,
        headers={"X-Request-ID": request_id},
    )


@app.get("/healthz")
async def live_health() -> dict[str, str]:
    return {"status": "ok", "service": "hook-studio"}


@app.get("/api/health")
async def protected_health(request: Request) -> dict:
    image = await request.app.state.queues.image.snapshot()
    video = await request.app.state.queues.video.snapshot()
    return {
        "status": "ok",
        "database": "ok",
        "queues": {"image": asdict(image), "video": asdict(video)},
        "recovered_jobs": request.app.state.recovered_jobs,
        "backup": request.app.state.backup_status,
    }


@app.get("/api/auth/session")
async def session(request: Request):
    principal = request.state.principal
    return {"principal": principal.model_dump(mode="json")}


if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "接口不存在"})
    index = DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail={"error_code": "FRONTEND_NOT_BUILT", "message": "前端尚未构建"})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
