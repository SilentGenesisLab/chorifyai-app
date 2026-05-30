# Chorify Backend (FastAPI)

Python backend for Chorify — **real file uploads** (image / audio / video / file →
Aliyun OSS) plus the 素材生产 AI generation endpoints (mocked for now).

The Next.js frontend reaches these via same-origin rewrites
(`/api/upload`, `/api/material/*` → this service), so no CORS is needed in prod.

## Run (dev)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on *nix)
pip install -r requirements.txt
copy .env.example .env          # then fill OSS keys (already set in .env here)
uvicorn app.main:app --reload --port 8000
```

- Health:    http://localhost:8000/health
- API docs:  http://localhost:8000/docs

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | liveness |
| POST | `/api/upload` | multipart upload → OSS. fields: `file`, `kind`=image\|audio\|video\|file. **real** |
| POST | `/api/material/generate` | start a 素材 generation job (mock) |
| GET  | `/api/material/jobs/{id}` | poll a job → processing/succeeded (kind=audio for 配音, else video) |

Upload returns `{ ok, url, key, kind, name, size }` — `url` is the public
`https://oss3.sligenai.cn/...` link.

Switch real AI on by setting `MOCK_MODE=false` and implementing the provider
branches in `app/routers/material.py`.
