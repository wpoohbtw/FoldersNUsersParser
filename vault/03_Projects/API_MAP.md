# API Map

## Accounts

Base prefix: `/api/v1`

Portal integration:

- Project does not implement local login.
- SoftPortal should proxy requests with `X-Portal-User-Id` and/or `X-Portal-Username`.
- Local development can emulate the current Portal user through `.env` keys `APP_ENV=development` and `PORTAL_DEV_USERNAME=wpoohbtw`.
- In `APP_ENV=production`, requests without Portal user headers return `401`.
- Account, import-job, phone-flow, avatar and future folder-parser data is scoped to the current Portal user when Portal headers or dev username are present.

### `GET /accounts`

Returns saved Telegram accounts from SQLite.

Optional headers:

```http
X-Portal-User-Id: portal-user-id
X-Portal-Username: wpoohbtw
```

Response:

```json
{
  "items": [
    {
      "account_id": 1,
      "user_id": 123,
      "phone": "+79990000000",
      "username": "@username",
      "first_name": "First",
      "last_name": "Last",
      "bio": "",
      "display_name": "First Last",
      "geo": "RU",
      "avatar_url": "/media/avatars/wpoohbtw/123.jpg",
      "session_name": "123_abcd1234",
      "source_type": "session",
      "portal_user_id": "",
      "portal_username": "wpoohbtw",
      "account_status": "valid",
      "checked_at": "2026-06-10T17:00:00Z",
      "created_at": "2026-06-10T17:00:00Z",
      "roles": []
    }
  ]
}
```

### `GET /me`

Returns the current Portal user context resolved from `X-Portal-User-Id` / `X-Portal-Username`, or from local development fallback.

Response:

```json
{
  "portal_user_id": "",
  "portal_username": "wpoohbtw"
}
```

### `POST /accounts/check`

Checks already saved accounts through Telethon sessions.

Uses the same Portal user scope as `GET /accounts`.

Request:

```json
{ "account_ids": [1] }
```

Response:

```json
{ "checked": 1, "failed": 0 }
```

## Folders

Future folder-parser tables are prepared with Portal ownership columns:

- `folder_listeners`
- `folder_parser_logs`
- `folder_channels`
- `processed_folder_links`

They are intended to keep listeners, parser logs, parsed channels and processed `t.me/addlist` links isolated per Portal user.

### `GET /folders/accounts/{account_id}/folders`

Returns saved Telegram dialog folders for the selected account.

Uses the same Portal user scope as `GET /accounts`.

Response:

```json
{
  "items": [
    {
      "id": "2",
      "title": "Market Watch",
      "channels": 38,
      "peers": 41,
      "updated_at": "2026-06-11T16:00:00Z"
    }
  ]
}
```

### `POST /folders/accounts/{account_id}/folders/refresh`

Reads real Telegram dialog folders from the selected account session through Telethon, saves them to SQLite, and returns the fresh list.

Uses the same Portal user scope as `GET /accounts`.

## Session Import

### `POST /imports/session/upload`

Accepts one or more `.session` files as multipart field `files`.

Flow:

- saves uploads to `backend/data/uploads`;
- validates each session with Telethon using `API_ID` and `API_HASH`;
- moves valid sessions into staged files under `backend/data/sessions`;
- creates `import_jobs` and `import_items`.
- binds the import job to the current Portal user.

Response:

```json
{ "job_id": "job_xxx" }
```

### `GET /imports/jobs/{job_id}`

Returns import job status and counters.
Returns `404` when the job belongs to another Portal user.

### `GET /imports/jobs/{job_id}/items`

Returns import items and any profile data already read during check.
Returns `404` when the job belongs to another Portal user.

### `POST /imports/jobs/{job_id}/check`

Reads staged sessions, fetches Telegram profile data, avatar, phone, username, display name, bio and geo.

Request:

```json
{ "item_ids": null }
```

## Phone Import

### `POST /imports/phone/start`

Starts Telegram login by phone number and sends a code request.
The created import job is bound to the current Portal user.

Request:

```json
{ "phone": "+79990000000" }
```

Response:

```json
{
  "flow_id": "phf_xxx",
  "job_id": "job_xxx",
  "next_step": "code"
}
```

### `POST /imports/phone/code`

Submits Telegram login code. If the account has 2FA, returns `next_step: "password"`.

Request:

```json
{ "flow_id": "phf_xxx", "code": "12345" }
```

### `POST /imports/phone/password`

Submits Telegram 2FA password and finalizes the phone import into a staged checked import item.

Request:

```json
{ "flow_id": "phf_xxx", "password": "secret" }
```

### `POST /imports/phone/cancel`

Cancels active phone login flow and removes temporary session file.

Request:

```json
{ "flow_id": "phf_xxx" }
```

### `POST /imports/jobs/{job_id}/save`

Moves checked staged sessions into final session files and upserts rows into `accounts`.

Request:

```json
{ "item_ids": null }
```
