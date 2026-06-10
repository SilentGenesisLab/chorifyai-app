# ChorifyAI Desktop

Electron wrapper for the existing Chorify Next.js web app and FastAPI backend.

## Development

From `frontend/`:

```powershell
pnpm install
pnpm --filter @chorify/desktop dev
```

The desktop shell starts:

- FastAPI backend on an available local port, preferring `8000`
- Next.js web app on an available local port, preferring `3001`
- Electron window loading the local Next.js URL

## Environment

Optional overrides:

```powershell
$env:CHORIFY_API_PORT="8000"
$env:CHORIFY_WEB_PORT="3001"
$env:CHORIFY_MOCK_MODE="true"
$env:LOCAL_STORAGE_ROOT="I:\ChorifyAI\workspace"
```

Desktop mode defaults to local file storage. Uploads, split clips, generated
materials, and batch-composed videos are written under `LOCAL_STORAGE_ROOT`.

## Build

```powershell
pnpm --filter @chorify/desktop build
```

## Package

The packaged mode expects the Next app to be built before packaging:

```powershell
pnpm --filter @chorify/web build
pnpm --filter @chorify/desktop dist
```

For a full production installer, bundle Python/FastAPI as a standalone executable
or include a managed Python runtime under Electron `extraResources`.
