from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    api_id: int
    api_hash: str
    app_env: str
    portal_dev_username: str
    db_path: Path
    sessions_dir: Path
    uploads_dir: Path
    avatars_dir: Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[2]
    _load_env_file(root_dir / ".env")

    api_id_raw = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    api_id = int(api_id_raw) if api_id_raw.isdigit() else 0
    app_env = os.getenv("APP_ENV", "development").strip().lower() or "development"
    portal_dev_username = os.getenv("PORTAL_DEV_USERNAME", "").strip()

    data_dir = root_dir / "backend" / "data"
    sessions_dir = data_dir / "sessions"
    uploads_dir = data_dir / "uploads"
    avatars_dir = data_dir / "avatars"

    sessions_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    avatars_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        app_env=app_env,
        portal_dev_username=portal_dev_username,
        db_path=data_dir / "folders_n_users_parser.db",
        sessions_dir=sessions_dir,
        uploads_dir=uploads_dir,
        avatars_dir=avatars_dir,
    )
