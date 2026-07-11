from pathlib import Path
from types import SimpleNamespace

import yaml
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.admin import router
from app.db import Database


def test_admin_can_update_code_and_settings(tmp_path: Path):
    codes = tmp_path / "codes.yaml"
    codes.write_text(yaml.safe_dump({"codes": [{"id": "admin", "code": "123456", "client_name": "管理", "role": "admin", "enabled": True}, {"id": "c1", "code": "abcdef", "client_name": "客户", "role": "client", "enabled": True}]} , allow_unicode=True), encoding="utf-8")
    db = Database(tmp_path / "db.sqlite3"); db.initialize()
    app = FastAPI(); app.include_router(router)
    app.state.db = db; app.state.settings = SimpleNamespace(access_codes_file=codes)
    @app.middleware("http")
    async def principal(request: Request, call_next):
        request.state.principal = {"role": "admin"}
        return await call_next(request)
    client = TestClient(app)
    assert client.patch("/api/admin/access-codes/c1", json={"daily_video_limit": 12}).status_code == 200
    assert client.patch("/api/admin/settings", json={"video_concurrency": 3}).json()["restart_required"]
    assert next(item for item in yaml.safe_load(codes.read_text(encoding="utf-8"))["codes"] if item["id"] == "c1")["daily_video_limit"] == 12


def test_non_admin_is_forbidden(tmp_path: Path):
    app = FastAPI(); app.include_router(router)
    @app.middleware("http")
    async def principal(request: Request, call_next):
        request.state.principal = {"role": "client"}
        return await call_next(request)
    assert TestClient(app).get("/api/admin/dashboard").status_code == 403


def test_admin_storyboard_runtime_tables_are_exportable(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    app = FastAPI()
    app.include_router(router)
    app.state.db = db
    app.state.settings = SimpleNamespace(access_codes_file=tmp_path / "codes.yaml")
    (tmp_path / "codes.yaml").write_text("codes: []\n", encoding="utf-8")

    @app.middleware("http")
    async def inject_admin(request, call_next):
        request.state.principal = SimpleNamespace(role="admin")
        return await call_next(request)

    client = TestClient(app)
    for table in ("storyboard_panels", "approval_decisions", "skill_runs", "workflow_events"):
        response = client.get("/api/admin/data/tables", params={"table": table})
        assert response.status_code == 200
        assert response.json()["table"] == table
