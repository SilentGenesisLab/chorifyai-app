# Chorify

An AI video-marketing platform — modeled on the structure of **Kuaizi (筷子科技)**.
Workflow modules (编导灵感 / 素材生产 / 合成量产 / 投放分发) plus services
(云盘 / 手机协同 / 直播切片 / 视频翻译 / 矩阵宝 / BGM市场 / 视频拆分).

> Iteration 1 scope: real backbone — **SMS auth · app shell · 开始工作 homepage**.
> Heavy AI (video generation / dubbing / digital humans) is **mocked** for now.

## Architecture

```
chorify/
├── apps/
│   ├── web/          Next.js 16 (App Router) — frontend + auth backend + AI proxy
│   └── ai-service/   Python FastAPI — AI modules (mocked in iteration 1)
├── packages/
│   └── db/           Prisma 6 schema + client (shared)
└── docker-compose.yml  Postgres 16 + Redis 7 (local dev infra)
```

| Layer | Choice |
|---|---|
| Frontend + auth/AI proxy | Next.js 16, React 19, Tailwind v4, TypeScript |
| AI modules | Python 3.10, FastAPI |
| Database | PostgreSQL 16 + Prisma 6 |
| Cache / codes / rate-limit | Redis 7 (ioredis) |
| Sessions | JWT (jose) in httpOnly cookie |
| File storage | Aliyun OSS (mock provider in dev) |
| SMS login | Aliyun SMS (mock provider in dev) |

## Quick start

Prerequisites: Node ≥ 20, pnpm 10, Docker, Python 3.10 (only for ai-service).

```bash
# 1. infra
docker compose up -d                      # postgres + redis

# 2. env
cp .env.example apps/web/.env
cp .env.example packages/db/.env          # only DATABASE_URL is needed here

# 3. install + db
pnpm install
pnpm db:generate
pnpm db:migrate                           # creates tables
pnpm db:seed                              # demo org + projects + assets

# 4. run
pnpm dev                                  # web on http://localhost:3001
```

> Windows note: use `127.0.0.1` (not `localhost`) in `DATABASE_URL`/`REDIS_URL` —
> Node resolves `localhost` to IPv6 `::1`, where Docker's published ports don't
> listen. The web dev server uses port **3001** (3000 is often taken).

SMS login in dev: `SMS_PROVIDER=mock` prints the 6-digit code to the **web server
console** — enter any phone number, read the code from the terminal.

### AI service (optional in iteration 1)

```bash
cd apps/ai-service
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## What's real vs mocked (iteration 1)

| Real | Mocked |
|---|---|
| SMS login flow, sessions, route protection | SMS delivery (code → console) |
| Postgres + Prisma models, seed data | OSS uploads (fake URLs) |
| App shell, navigation, homepage from DB | Video gen / dubbing / digital human |
| FastAPI service skeleton + endpoints | AI outputs (placeholder responses) |

## Branding

The product name lives in one place: `apps/web/src/lib/brand.ts`
(`NEXT_PUBLIC_APP_NAME`). Change it once to re-brand the whole UI.
