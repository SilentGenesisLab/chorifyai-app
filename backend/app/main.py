from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import local_storage, material, mix, split, translate, upload, voice
from app.services.local_storage import storage_root

app = FastAPI(title="Chorify Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(local_storage.router)
app.include_router(local_storage.files_router)
app.include_router(material.router)
app.include_router(voice.router)
app.include_router(split.router)
app.include_router(mix.router)
app.include_router(translate.router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "chorify-backend",
        "version": "0.1.0",
        "mock_mode": settings.mock_mode,
        "oss_provider": settings.oss_provider,
        "local_storage_root": str(storage_root()),
    }
