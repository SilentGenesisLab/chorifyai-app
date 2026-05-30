from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import material, compose

app = FastAPI(title="Chorify AI Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(material.router)
app.include_router(compose.router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "chorify-ai-service",
        "version": "0.1.0",
        "mock_mode": settings.mock_mode,
    }
