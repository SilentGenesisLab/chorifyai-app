# Hook Studio Full Storyboard MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute this plan task-by-task. Every task ends with executable evidence and an Inspector checkpoint.

**Goal:** Replace the current one-image-per-shot chat demo with a production MVP where every video shot has a complete shot contract, reviewable storyboard panels, a clean generation frame, versioned approval, live execution events, an animatic, and an enforceable server-side production gate.

**Architecture:** Keep Hook Studio as a FastAPI/React modular monolith and customer control plane. Persist workflow facts in SQLite, stream durable events with SSE, store media in OSS, and call the AI Video Kernel through server-only adapters. Do not expose provider names, provider identifiers, prompts, or secrets to the customer UI.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLite WAL, asyncio, httpx, React, TypeScript, Vite, existing lucide-react, FFmpeg, Playwright.

## Global Constraints

- No new runtime dependencies.
- Every video shot has at least one required storyboard panel and one selected clean 9:16 frame.
- A storyboard cannot enter video production until every shot and required panel is approved and the animatic is confirmed.
- A provider invocation is 4-15 seconds. Longer projects are multiple shots plus assembly.
- Image and video concurrency remain separate. Daily image limit is 1000; global daily video limit is 100.
- Failed video submissions release reserved quota. Storyboard revisions only charge newly generated image candidates.
- Annotated boards are for people; only clean assets marked `send_to_provider=true` can be sent to the Kernel.
- Frontend responses and DOM do not expose model or provider names.
- All mutations are tenant-scoped, version checked, and idempotent where an external call can occur.

---

### Task 1: Durable storyboard and workflow contracts

**Files:**
- Modify: `app/db.py`
- Modify: `app/repositories/workspace.py`
- Create: `app/storyboard_runtime.py`
- Test: `tests/test_full_storyboard.py`

**Produces:** Versioned Shot, Panel, SkillRun, ApprovalDecision, WorkflowEvent, and Animatic records plus repository methods that always tenant-filter reads.

- [ ] Add failing migration and repository tests for Panel 1:N, append-only approvals, event replay, and approved snapshot immutability.
- [ ] Add additive SQLite tables and indexes without rewriting existing production rows.
- [ ] Implement typed runtime contracts and deterministic panel planning.
- [ ] Run `pytest tests/test_db_migrations.py tests/test_full_storyboard.py -q` and require zero failures.
- [ ] Inspector checkpoint N1.

### Task 2: Skill runtime and production gate

**Files:**
- Create: `app/skill_runtime.py`
- Modify: `app/services/planning.py`
- Modify: `app/services/production.py`
- Test: `tests/test_skill_runtime.py`

**Produces:** `BriefCompiler`, `StoryboardCompiler`, `PanelPlanner`, `ReferenceManifestCompiler`, `ShotGateValidator`, `PromptCompiler`, `ApprovalPolicy`, and persisted public/private traces.

- [ ] Add failing tests proving missing Panel, clean frame, approval, invalid duration, or stale version blocks production before quota reservation.
- [ ] Compile every planner result into complete shot fields and panel roles.
- [ ] Persist each Skill transition with input/output hash, decision, evidence, retry count, and public display label.
- [ ] Generate clean panel candidates using the image queue; keep annotation metadata separate from clean image bytes.
- [ ] Run focused planning, Skill, quota, and production tests.
- [ ] Inspector checkpoint N2.

### Task 3: Durable SSE communication

**Files:**
- Create: `app/services/workflow_events.py`
- Modify: `app/api/workspace.py`
- Modify: `app/main.py`
- Test: `tests/test_workflow_events.py`

**Produces:** `GET /api/studio/tasks/{task_id}/events` with cookie authentication, tenant isolation, Last-Event-ID replay, heartbeat, and DB-first event delivery.

- [ ] Add failing tests for unauthenticated 401, cross-client 404, ordered replay, heartbeat, and reconnect.
- [ ] Write task and Skill state changes to SQLite in the same transaction as their business mutation.
- [ ] Stream stable `hook.event.v1` envelopes and set `X-Accel-Buffering: no`.
- [ ] Return measured counts or indeterminate provider wait; never invent provider progress.
- [ ] Run SSE and workspace API tests.
- [ ] Inspector checkpoint N3.

### Task 4: Per-panel revision, approval, and animatic

**Files:**
- Modify: `app/api/workspace.py`
- Modify: `app/services/production.py`
- Modify: `app/services/media_ops.py`
- Modify: `app/repositories/workspace.py`
- Test: `tests/test_storyboard_workflow.py`

**Produces:** Storyboard detail, draft shot patch, panel regenerate, scoped decisions, animatic creation, final freeze, and production endpoints.

- [ ] Add APIs for storyboard detail, shot patch, panel regenerate, scoped decisions, animatic, and production.
- [ ] Render a 9:16 MP4 animatic from selected clean frames using exact shot durations and existing FFmpeg.
- [ ] Freeze an approved snapshot hash and reject edits or stale approvals with 409.
- [ ] Preserve unchanged panels and only rerun the selected panel.
- [ ] Reserve video quota only in the final approval transaction.
- [ ] Run storyboard workflow, quota, and media tests.
- [ ] Inspector checkpoint N4.

### Task 5: Customer interaction and three synchronized views

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/e2e/full-storyboard-mvp.spec.ts`

**Produces:** Persistent requirement/coverage/approval cards; synchronized shot table, filmstrip, and animatic; per-panel revision and approval; asset/preview/final right rail; SSE progress.

- [ ] Add typed Storyboard, Shot, Panel, SkillStage, Approval, Animatic, and WorkflowEvent models.
- [ ] Replace four-second workspace polling for active runs with SSE plus snapshot recovery.
- [ ] Show `shot N/N | panel N/N | clean N/N | approved X/N` and disable production while any server guard is false.
- [ ] Implement per-shot selection, annotated/clean toggle, feedback, regenerate, approve, version display, and animatic confirmation.
- [ ] Keep task execution cards in the conversation; keep the right rail limited to assets, selected preview, and final outputs.
- [ ] Verify desktop 1440x1000 and mobile 390x844 without overlap or horizontal overflow.
- [ ] Inspector checkpoint N5.

### Task 6: Kernel call contract and reliability

**Files:**
- Modify: `app/providers/kernel.py`
- Modify: `app/services/production.py`
- Test: `tests/test_kernel_provider.py`
- Test: `tests/test_generation_service.py`

**Produces:** Explicit generation mode contract, idempotent submit/poll behavior, real provider queue facts when available, retry trace, tail-frame continuity, and technical plus semantic QC gates.

- [ ] Keep the verified multimodal route as the default MVP path and label unprobed routes unavailable.
- [ ] Send only clean approved assets selected by `send_to_provider` and a persisted reference manifest.
- [ ] Never resubmit after receiving a provider submit ID; poll that ID until terminal state or recoverable timeout.
- [ ] Extract an accepted segment tail frame for the next shot continuity candidate.
- [ ] Persist request, task, shot, panel, and trace identifiers without returning provider identifiers to the browser.
- [ ] Run fake Kernel integration and a budget-ledger-approved real smoke test.
- [ ] Inspector checkpoint N6.

### Task 7: Verification, deployment, and evidence

**Files:**
- Create: `ops/rounds/full-storyboard-mvp/gate.md`
- Create: `ops/rounds/full-storyboard-mvp/verification.md`
- Create: `ops/rounds/full-storyboard-mvp/review.md`
- Modify: `OPERATOR_MANUAL.md`
- Modify: `TEST_PLAN.md`

**Produces:** Reproducible unit/integration/browser/security evidence, public deployment, exact build identity, and an operator-ready handoff.

- [ ] Run the full Python suite and frontend production build with logs.
- [ ] Run secret scans, tenant isolation probes, 401/404/409/422 gates, quota reconciliation, restart recovery, and backup verification.
- [ ] Run Playwright for login, full-shot coverage, panel-only revision, version conflict, animatic approval, SSE reconnect, real submission unlock, right rail, and mobile layout.
- [ ] Deploy the approved build through systemd/Nginx without exposing secrets and add build SHA/schema/skill-pack versions to `/healthz`.
- [ ] Run public health, auth, static asset, SSE, and authenticated browser smoke tests.
- [ ] Give all evidence to the independent Inspector; final result must be PASS before tagging and publishing.

## Self-Review

- Spec coverage: full-shot boards, clean frames, descriptions, Skill display, API, communication, tools, calls, storage, observability, approval, quotas, testing, deployment, and operations are each assigned to a task.
- Placeholder scan: no deferred implementation marker is accepted by this plan.
- Type consistency: Storyboard contains Shot 1:N Panel; Panel owns candidate and selected asset references; production consumes only the approved frozen snapshot.

