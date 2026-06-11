# AI Changelog

## 2026-06-10

- Added FastAPI backend with SQLite storage for Telegram account import and account validity checks.
- Added Telethon `.session` import pipeline: upload, staged validation, profile check, save to accounts.
- Replaced frontend mock accounts with live `/api/v1` API calls.
- Updated the shared `start.bat` launcher to install backend dependencies, create `.venv`, start backend, and start Vite frontend.
- Added phone-number authorization import flow: phone start, code submit, optional 2FA password, cancel, staged import item, and frontend queue UI.
- Added SoftPortal ownership groundwork: account/import data can be scoped by `X-Portal-User-Id` / `X-Portal-Username`, local dev can emulate `wpoohbtw`, and existing accounts are migrated to `wpoohbtw`.

## 2026-06-11

- Added real Telegram folder loading endpoint for selected accounts and connected the Folders page to it.
- Persisted the active frontend page across browser refreshes.
- Hardened SoftPortal ownership groundwork: production now requires Portal user headers, `/api/v1/me` exposes current Portal context, phone import flows are owner-checked, avatars are stored per Portal user, Folders localStorage keys are user-scoped, and future folder-parser SQLite tables include Portal ownership columns.
- Prepared the project for GitHub upload with repository metadata, source-safe ignore rules, README instructions, and explicit inclusion of `AGENTS.md` and `vault/`.
