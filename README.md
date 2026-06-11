# FoldersNUsersParser

Telegram account and folder-channel parser workspace.

## Stack

- Frontend: React, TypeScript, Vite, CSS, lucide-react
- Backend: Python, FastAPI, Pydantic, SQLite, uvicorn, Telethon
- API prefix: `/api/v1`

## Local Start

1. Copy `.env.example` to `.env`.
2. Fill `API_ID`, `API_HASH` and `PORTAL_DEV_USERNAME`.
3. Run:

```bat
start.bat
```

The launcher installs dependencies if needed and starts:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

## Portal Auth Model

This project does not implement its own login. In production SoftPortal should proxy requests and pass:

- `X-Portal-User-Id`
- `X-Portal-Username`

Set `APP_ENV=production` on the server to require those headers.

## Repository Notes

The repository intentionally includes:

- `AGENTS.md`
- `vault/`
- source code
- dependency manifests
- `.env.example`

The repository intentionally ignores:

- `.env`
- `.venv/`
- `node_modules/`
- `dist/`
- `backend/data/`
- Telethon `.session` files
- SQLite databases and WAL/SHM files
