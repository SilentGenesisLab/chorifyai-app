# Chorify AI Service (FastAPI)

Houses the heavy AI modules. In iteration 1 every endpoint runs in
**mock mode** (`MOCK_MODE=true`) and returns placeholder results, so the
web app can integrate against a stable contract before real providers
(Seedance / TTS / digital-human / ffmpeg render) are wired in.

## Run (dev)

```bash
cd apps/ai-service
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on *nix)
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- Health:    http://localhost:8000/health
- API docs:  http://localhost:8000/docs

## Endpoints (mocked)

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | liveness + mock flag |
| POST | `/api/material/generate` | start an AI素材生产 job (AI影棚/复刻/配音/数字人) |
| GET  | `/api/material/jobs/{job_id}` | poll a generation job |
| POST | `/api/compose/mix` | produce N 智能混剪 combinations |

Wire real providers by setting `MOCK_MODE=false` and implementing the
`TODO`/`NotImplementedError` branches in `app/routers/*`.
