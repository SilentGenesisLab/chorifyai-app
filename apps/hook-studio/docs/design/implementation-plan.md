# Hook Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use bounded subagent-driven development with review between independently testable modules. Steps use checkbox syntax for tracking.

**Goal:** Build, publish, deploy, and verify the Hook Studio v1 Chinese image/video hook generator.

**Architecture:** A FastAPI modular monolith owns authentication, SQLite, separate image/video queues, quotas, events, skill policy gates, provider proxying, backups, insights, and the admin API. A React/Vite SPA is built into static assets served by FastAPI and deployed behind Nginx at `/hook-studio/`.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, aiosqlite, httpx, PyYAML, itsdangerous, React 19, Vite, TypeScript, lucide-react, pytest, Playwright, systemd, Nginx.

## Global Constraints

- Provider secrets remain server-side only.
- Every protected API returns 401 without a valid session.
- Video daily hard limit is 100 globally per UTC+8 day; client sub-limits are configurable.
- Images have no daily count limit; image and video concurrency are independent.
- Seedance clips are 4-5 seconds, 9:16, with native-audio intent and postflight audio verification.
- Provider timeout gets at most one retry.
- Events double-write to SQLite and JSONL.
- Customer delete is soft delete; physical OSS artifact remains.
- No paid generation before local auth, quota, event, and skill-gate tests pass.

---

### Task 1: Repository And Contracts

**Files:** `README.md`, `pyproject.toml`, `.gitignore`, `.env.example`, `config/access_codes.example.yaml`, `config/presets-v1.yaml`, `app/models.py`, `app/settings.py`, `tests/test_settings.py`

- [ ] Create `uat` and `feature/hook-studio-v1` in `SilentGenesisLab/chorifyai-app`, with code isolated under `apps/hook-studio/`.
- [ ] Define settings, request/response models, error codes, access-code example, and versioned preset schema.
- [ ] Add tests proving secrets have no defaults and runtime directories are ignored.
- [ ] Run `pytest tests/test_settings.py -q`; expect PASS.
- [ ] Commit and push `chore: bootstrap hook studio contracts`.

### Task 2: Persistence, Auth, Quota, Events

**Files:** `app/db.py`, `app/auth.py`, `app/quota.py`, `app/events.py`, `app/api/auth.py`, `tests/test_auth.py`, `tests/test_quota.py`, `tests/test_events.py`

- [ ] Create migrations for jobs, events, daily usage, settings, and backup records.
- [ ] Implement access-code login and signed HttpOnly session cookies.
- [ ] Implement global video reservation and customer sub-limit in one SQLite transaction.
- [ ] Implement SQLite plus JSONL event writes with stable code IDs.
- [ ] Run targeted tests; expect 401 without code, UTC+8 reset correctness, hard-cap rejection, and dual-write PASS.
- [ ] Commit and push `feat: add auth quota and event ledger`.

### Task 3: Skill Policy And Provider Adapter

**Files:** `app/skill_policy.py`, `app/providers/kernel.py`, `app/qc.py`, `config/skill-policy-v1.yaml`, `tests/test_skill_policy.py`, `tests/test_kernel_provider.py`, `tests/test_qc.py`

- [ ] Implement deterministic Seedance reference, slot, action-causality, duration, ratio, audio-intent, and prohibited-element checks.
- [ ] Implement Kernel storage upload, GPT Image call, Seedance submit/poll/cancel, timeouts, and one retry.
- [ ] Implement video postflight metadata and audio checks.
- [ ] Test with mocked Kernel responses and local ffprobe fixtures.
- [ ] Commit and push `feat: add observable skill-gated generation`.

### Task 4: Durable Separate Queues

**Files:** `app/queues.py`, `app/services/generation.py`, `app/api/studio.py`, `tests/test_queues.py`, `tests/test_generation_service.py`

- [ ] Implement separate image and video queues with independent semaphores.
- [ ] Persist before enqueue and recover queued/running work on startup.
- [ ] Compute queue position and mode-specific ETA.
- [ ] Release video reservation on failed preflight/provider/postflight; retain succeeded usage.
- [ ] Test concurrency isolation, recovery, retry, and status transitions.
- [ ] Commit and push `feat: add durable generation queues`.

### Task 5: Gallery, Admin, Backup, Insights

**Files:** `app/api/admin.py`, `app/backup.py`, `app/insights.py`, `app/main.py`, `tests/test_admin.py`, `tests/test_backup_restore.py`, `tests/test_insights.py`

- [ ] Implement gallery actions and soft delete.
- [ ] Implement admin usage, code enable/disable, quota and concurrency settings.
- [ ] Implement backup archive, OSS upload, 30-copy retention metadata, and restore verification.
- [ ] Implement download-rate stats, weekly ordering, A/B allocation records, Hook Insights, and digest Markdown.
- [ ] Run targeted tests and a local restore drill.
- [ ] Commit and push `feat: add operations and learning loop`.

### Task 6: Chinese SPA

**Files:** `frontend/src/*`, `frontend/package.json`, `frontend/vite.config.ts`, `app/static.py`, `tests/test_static_app.py`

- [ ] Build access-code login, three-step generator, preset controls, reference upload, balance, queue, gallery, and admin views.
- [ ] Use lucide icons, accessible controls, responsive 9:16 previews, stable dimensions, and Chinese operational copy.
- [ ] Add loading, empty, disabled, error, and recovery states without white screens.
- [ ] Build frontend and serve under `/hook-studio/`.
- [ ] Commit and push `feat: build hook studio web app`.

### Task 7: Local Security And E2E Gate

**Files:** `tests/e2e/*`, `playwright.config.ts`, `scripts/security_check.py`, `TEST_PLAN.md`, `SECURITY_REPORT.md`

- [ ] Run full pytest, frontend build, TypeScript, secret scan, and bundle scan.
- [ ] Run Playwright against local fake-provider mode for both modes and admin.
- [ ] Verify no-code 401, cross-client isolation, quota rejection, error recovery, and event export.
- [ ] Record results in test and security reports.
- [ ] Commit and push `test: verify local hook studio flows`.

### Task 8: GitHub Promotion And Deployment

**Files:** `deploy/hook-studio.service`, `deploy/nginx-hook-studio.conf`, `deploy/deploy.py`, `OPERATOR_MANUAL.md`

- [ ] Push incremental commits to `SilentGenesisLab/chorifyai-app` on `feature/hook-studio-v1` without modifying existing application directories.
- [ ] Merge feature into `uat`, deploy `/opt/hook-studio`, create remote secret files with mode 600, and configure systemd/Nginx.
- [ ] Run remote health, auth, database, and backup checks.
- [ ] Run three real image and three real video jobs within the 15-minute wait policy; record late jobs without duplicate submission.
- [ ] Run Playwright against the public URL and capture desktop/mobile screenshots.
- [ ] Promote tested `uat` to `main`, tag v1.0.0, and finalize operator manual.
- [ ] Commit and push `release: deploy hook studio v1`.
