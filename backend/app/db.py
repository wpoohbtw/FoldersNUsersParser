from __future__ import annotations

import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INITIAL_OWNER_USERNAME = "wpoohbtw"
INITIAL_OWNER_MIGRATION_KEY = "bind_existing_accounts_to_wpoohbtw_v1"


class Database:
    def __init__(self, db_path: Path) -> None:
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=10000")

    def __getattribute__(self, name: str) -> Any:
        attr = object.__getattribute__(self, name)
        if name.startswith("_") or not callable(attr) or getattr(attr, "__self__", None) is not self:
            return attr

        def locked_method(*args: Any, **kwargs: Any) -> Any:
            with object.__getattribute__(self, "_lock"):
                return attr(*args, **kwargs)

        return locked_method

    def init(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_user_id TEXT,
                portal_username TEXT,
                user_id INTEGER NOT NULL,
                phone TEXT,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                bio TEXT,
                display_name TEXT,
                geo TEXT,
                avatar_path TEXT,
                session_name TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                account_status TEXT NOT NULL DEFAULT 'valid',
                checked_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS import_jobs (
                id TEXT PRIMARY KEY,
                portal_user_id TEXT,
                portal_username TEXT,
                import_type TEXT NOT NULL,
                status TEXT NOT NULL,
                total INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS account_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                folder_id TEXT NOT NULL,
                title TEXT NOT NULL,
                channels INTEGER NOT NULL DEFAULT 0,
                peers INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(account_id, folder_id),
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS folder_listeners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_user_id TEXT,
                portal_username TEXT,
                account_id INTEGER NOT NULL,
                folder_id TEXT NOT NULL,
                folder_title TEXT,
                status TEXT NOT NULL DEFAULT 'idle',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS folder_parser_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_user_id TEXT,
                portal_username TEXT,
                listener_id INTEGER,
                log_type TEXT NOT NULL,
                event_type TEXT,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(listener_id) REFERENCES folder_listeners(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS folder_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER,
                portal_user_id TEXT,
                portal_username TEXT,
                channel_id INTEGER NOT NULL,
                account_id INTEGER,
                folder_id TEXT,
                username TEXT,
                title TEXT NOT NULL,
                link TEXT,
                avatar_path TEXT,
                subscribers INTEGER NOT NULL DEFAULT 0,
                avg_views_10 INTEGER NOT NULL DEFAULT 0,
                source_count INTEGER NOT NULL DEFAULT 0,
                source_channels_json TEXT,
                review_status TEXT NOT NULL DEFAULT 'unchecked',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_portal_user_id TEXT,
                owner_portal_username TEXT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_table_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                portal_user_id TEXT,
                portal_username TEXT,
                role TEXT NOT NULL DEFAULT 'editor',
                created_at TEXT NOT NULL,
                FOREIGN KEY(table_id) REFERENCES channel_tables(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_folder_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_user_id TEXT,
                portal_username TEXT,
                addlist_slug TEXT NOT NULL,
                link_url TEXT NOT NULL,
                first_channel_id INTEGER,
                channels_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'processing',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS import_items (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                account_id INTEGER,
                source_type TEXT,
                file_format TEXT,
                user_id INTEGER,
                phone TEXT,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                bio TEXT,
                display_name TEXT,
                geo TEXT,
                avatar_path TEXT,
                staged_session_name TEXT,
                is_saved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES import_jobs(id) ON DELETE CASCADE,
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE SET NULL
            )
            """
        )
        self.conn.commit()

        self._ensure_accounts_owner_schema()
        for table, column, definition in (
            ("accounts", "portal_user_id", "TEXT"),
            ("accounts", "portal_username", "TEXT"),
            ("import_items", "first_name", "TEXT"),
            ("import_items", "last_name", "TEXT"),
            ("import_items", "bio", "TEXT"),
            ("accounts", "checked_at", "TEXT"),
            ("import_jobs", "portal_user_id", "TEXT"),
            ("import_jobs", "portal_username", "TEXT"),
            ("folder_channels", "account_id", "INTEGER"),
            ("folder_channels", "folder_id", "TEXT"),
            ("folder_channels", "table_id", "INTEGER"),
            ("folder_channels", "review_status", "TEXT NOT NULL DEFAULT 'unchecked'"),
            ("folder_parser_logs", "event_type", "TEXT"),
            ("processed_folder_links", "status", "TEXT NOT NULL DEFAULT 'processing'"),
        ):
            self._ensure_column(table, column, definition)
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_folder_listeners_owner_account_folder
            ON folder_listeners(
                COALESCE(portal_user_id, ''),
                COALESCE(portal_username, ''),
                account_id,
                folder_id
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_folder_parser_logs_owner_created
            ON folder_parser_logs(
                COALESCE(portal_user_id, ''),
                COALESCE(portal_username, ''),
                created_at
            )
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_folder_channels_owner_channel
            ON folder_channels(
                COALESCE(portal_user_id, ''),
                COALESCE(portal_username, ''),
                channel_id
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_folder_channels_table_channel
            ON folder_channels(table_id, channel_id)
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_tables_owner
            ON channel_tables(
                COALESCE(owner_portal_user_id, ''),
                COALESCE(owner_portal_username, '')
            )
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_table_access_user
            ON channel_table_access(
                table_id,
                COALESCE(portal_user_id, ''),
                COALESCE(portal_username, '')
            )
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_processed_folder_links_owner_slug
            ON processed_folder_links(
                COALESCE(portal_user_id, ''),
                COALESCE(portal_username, ''),
                addlist_slug
            )
            """
        )
        self.conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_owner_user
            ON accounts(
                COALESCE(portal_user_id, ''),
                COALESCE(portal_username, ''),
                user_id
            )
            """
        )
        self.conn.commit()
        self._bind_existing_accounts_once()
        self._ensure_existing_channel_tables()

    def _ensure_accounts_owner_schema(self) -> None:
        if not self._has_legacy_user_id_unique():
            return

        self.conn.execute("ALTER TABLE accounts RENAME TO accounts_legacy_owner_migration")
        self.conn.execute(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_user_id TEXT,
                portal_username TEXT,
                user_id INTEGER NOT NULL,
                phone TEXT,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                bio TEXT,
                display_name TEXT,
                geo TEXT,
                avatar_path TEXT,
                session_name TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                account_status TEXT NOT NULL DEFAULT 'valid',
                checked_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        legacy_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(accounts_legacy_owner_migration)").fetchall()}
        portal_user_expr = "portal_user_id" if "portal_user_id" in legacy_columns else "NULL"
        portal_username_expr = "portal_username" if "portal_username" in legacy_columns else "NULL"
        first_name_expr = "first_name" if "first_name" in legacy_columns else "NULL"
        last_name_expr = "last_name" if "last_name" in legacy_columns else "NULL"
        bio_expr = "bio" if "bio" in legacy_columns else "NULL"
        checked_at_expr = "checked_at" if "checked_at" in legacy_columns else "NULL"
        self.conn.execute(
            f"""
            INSERT INTO accounts(
                id, portal_user_id, portal_username, user_id, phone, username, first_name, last_name,
                bio, display_name, geo, avatar_path, session_name, source_type, account_status,
                checked_at, created_at
            )
            SELECT
                id, {portal_user_expr}, {portal_username_expr}, user_id, phone, username, {first_name_expr}, {last_name_expr},
                {bio_expr}, display_name, geo, avatar_path, session_name, source_type, account_status,
                {checked_at_expr}, created_at
            FROM accounts_legacy_owner_migration
            """
        )
        self.conn.execute("DROP TABLE accounts_legacy_owner_migration")
        self.conn.commit()

    def _has_legacy_user_id_unique(self) -> bool:
        try:
            indexes = self.conn.execute("PRAGMA index_list(accounts)").fetchall()
        except sqlite3.OperationalError:
            return False
        for index in indexes:
            if not int(index["unique"]):
                continue
            columns = [
                row["name"]
                for row in self.conn.execute(f"PRAGMA index_info({index['name']})").fetchall()
                if row["name"]
            ]
            if columns == ["user_id"]:
                return True
        return False

    def _bind_existing_accounts_once(self) -> None:
        row = self.conn.execute("SELECT value FROM app_meta WHERE key = ? LIMIT 1", (INITIAL_OWNER_MIGRATION_KEY,)).fetchone()
        if row:
            return
        self.conn.execute(
            """
            UPDATE accounts
            SET portal_username = ?
            WHERE portal_user_id IS NULL
              AND (portal_username IS NULL OR portal_username = '')
            """,
            (INITIAL_OWNER_USERNAME,),
        )
        self.conn.execute(
            "INSERT INTO app_meta(key, value) VALUES(?, ?)",
            (INITIAL_OWNER_MIGRATION_KEY, _utc_now()),
        )
        self.conn.commit()

    def _ensure_existing_channel_tables(self) -> None:
        rows = self.conn.execute(
            """
            SELECT DISTINCT portal_user_id, portal_username
            FROM folder_channels
            WHERE table_id IS NULL
            """
        ).fetchall()
        for row in rows:
            portal_user_id = row["portal_user_id"] or ""
            portal_username = row["portal_username"] or ""
            table_id = self.ensure_channel_table(portal_user_id, portal_username)
            where, args = self._owner_where(portal_user_id, portal_username)
            self.conn.execute(
                f"UPDATE folder_channels SET table_id = ? WHERE table_id IS NULL AND {where}",
                (table_id, *args),
            )
        self.conn.commit()

    def bind_portal_username_to_user_id(self, portal_user_id: str, portal_username: str) -> None:
        portal_user_id = str(portal_user_id or "").strip()
        portal_username = str(portal_username or "").strip()
        if not portal_user_id or not portal_username:
            return

        old_table = self.conn.execute(
            """
            SELECT id FROM channel_tables
            WHERE owner_portal_user_id IS NULL AND owner_portal_username = ?
            LIMIT 1
            """,
            (portal_username,),
        ).fetchone()
        current_table = self.conn.execute(
            """
            SELECT id FROM channel_tables
            WHERE owner_portal_user_id = ?
            LIMIT 1
            """,
            (portal_user_id,),
        ).fetchone()

        if old_table and current_table and int(old_table["id"]) != int(current_table["id"]):
            old_table_id = int(old_table["id"])
            current_table_id = int(current_table["id"])
            old_access_rows = self.conn.execute(
                """
                SELECT portal_user_id, portal_username, role
                FROM channel_table_access
                WHERE table_id = ?
                """,
                (old_table_id,),
            ).fetchall()
            self.conn.execute("UPDATE folder_channels SET table_id = ? WHERE table_id = ?", (current_table_id, old_table_id))
            for access in old_access_rows:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO channel_table_access (
                        table_id,
                        portal_user_id,
                        portal_username,
                        role
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        current_table_id,
                        access["portal_user_id"],
                        access["portal_username"],
                        access["role"],
                    ),
                )
            self.conn.execute("DELETE FROM channel_table_access WHERE table_id = ?", (old_table_id,))
            self.conn.execute("DELETE FROM channel_tables WHERE id = ?", (old_table_id,))
        elif old_table:
            old_table_id = int(old_table["id"])
            self.conn.execute(
                """
                UPDATE channel_tables
                SET owner_portal_user_id = ?
                WHERE id = ?
                """,
                (portal_user_id, old_table_id),
            )
            self.conn.execute(
                """
                UPDATE channel_table_access
                SET portal_user_id = ?
                WHERE table_id = ?
                  AND portal_user_id IS NULL
                  AND portal_username = ?
                """,
                (portal_user_id, old_table_id, portal_username),
            )

        for table in (
            "accounts",
            "import_jobs",
            "folder_listeners",
            "folder_parser_logs",
            "folder_channels",
            "processed_folder_links",
        ):
            self.conn.execute(
                f"""
                UPDATE {table}
                SET portal_user_id = ?
                WHERE portal_user_id IS NULL
                  AND portal_username = ?
                """,
                (portal_user_id, portal_username),
            )
        self.conn.execute(
            """
            UPDATE channel_table_access
            SET portal_user_id = ?
            WHERE portal_user_id IS NULL
              AND portal_username = ?
            """,
            (portal_user_id, portal_username),
        )
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        if column in {row["name"] for row in rows}:
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_job(
        self,
        job_id: str,
        import_type: str,
        total: int,
        status: str = "queued",
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO import_jobs(id, portal_user_id, portal_username, import_type, status, total, success, failed, created_at)
            VALUES(?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (job_id, portal_user_id or None, portal_username or None, import_type, status, int(total), _utc_now()),
        )
        self.conn.commit()

    def set_job_status(self, job_id: str, status: str, finished: bool = False) -> None:
        self.conn.execute(
            "UPDATE import_jobs SET status = ?, finished_at = COALESCE(?, finished_at) WHERE id = ?",
            (status, _utc_now() if finished else None, job_id),
        )
        self.conn.commit()

    def increment_job_counts(self, job_id: str, success_inc: int = 0, failed_inc: int = 0) -> None:
        self.conn.execute(
            "UPDATE import_jobs SET success = success + ?, failed = failed + ? WHERE id = ?",
            (int(success_inc), int(failed_inc), job_id),
        )
        self.conn.commit()

    def get_job(self, job_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM import_jobs WHERE id = ? LIMIT 1", (job_id,)).fetchone()
        return dict(row) if row else None

    def create_item(self, item_id: str, job_id: str, filename: str, status: str, source_type: str, file_format: str) -> None:
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO import_items(
                id, job_id, filename, status, message, account_id,
                source_type, file_format, user_id, phone, username, first_name, last_name,
                bio, display_name, geo, avatar_path, staged_session_name, is_saved,
                created_at, updated_at
            )
            VALUES(
                ?, ?, ?, ?, NULL, NULL,
                ?, ?, NULL, NULL, NULL, NULL, NULL,
                NULL, NULL, NULL, NULL, NULL, 0,
                ?, ?
            )
            """,
            (item_id, job_id, filename, status, source_type, file_format, now, now),
        )
        self.conn.commit()

    def update_item(self, item_id: str, status: str, message: str = "", account_id: int | None = None) -> None:
        self.conn.execute(
            """
            UPDATE import_items
            SET status = ?, message = ?, account_id = COALESCE(?, account_id), updated_at = ?
            WHERE id = ?
            """,
            (status, message, account_id, _utc_now(), item_id),
        )
        self.conn.commit()

    def update_item_fields(self, item_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _utc_now()
        assignments = []
        values: list[Any] = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(value)
        values.append(item_id)
        self.conn.execute(f"UPDATE import_items SET {', '.join(assignments)} WHERE id = ?", tuple(values))
        self.conn.commit()

    def list_items(self, job_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM import_items WHERE job_id = ? ORDER BY created_at", (job_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_unsaved_items(self, job_id: str, item_ids: list[str] | None = None) -> list[dict]:
        args: list[Any] = [job_id]
        where = "job_id = ? AND is_saved = 0 AND status IN ('done', 'checked')"
        if item_ids:
            placeholders = ",".join(["?"] * len(item_ids))
            where += f" AND id IN ({placeholders})"
            args.extend(item_ids)
        rows = self.conn.execute(f"SELECT * FROM import_items WHERE {where} ORDER BY created_at", tuple(args)).fetchall()
        return [dict(row) for row in rows]

    def upsert_account(
        self,
        user_id: int,
        phone: str,
        username: str,
        first_name: str,
        last_name: str,
        bio: str,
        display_name: str,
        geo: str,
        avatar_path: str,
        session_name: str,
        source_type: str,
        account_status: str = "valid",
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> int:
        now = _utc_now()
        existing = self._find_account_for_owner(int(user_id), portal_user_id, portal_username)
        if existing:
            account_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE accounts
                SET portal_user_id = COALESCE(?, portal_user_id),
                    portal_username = COALESCE(?, portal_username),
                    phone = ?, username = ?, first_name = ?, last_name = ?, bio = ?, display_name = ?, geo = ?,
                    avatar_path = ?, session_name = ?, source_type = ?, account_status = ?, checked_at = ?
                WHERE id = ?
                """,
                (
                    portal_user_id or None,
                    portal_username or None,
                    phone,
                    username,
                    first_name,
                    last_name,
                    bio,
                    display_name,
                    geo,
                    avatar_path,
                    session_name,
                    source_type,
                    account_status,
                    now,
                    account_id,
                ),
            )
            self.conn.commit()
            return account_id

        cur = self.conn.execute(
            """
            INSERT INTO accounts(
                portal_user_id, portal_username, user_id, phone, username, first_name, last_name, bio, display_name, geo,
                avatar_path, session_name, source_type, account_status, checked_at, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                portal_user_id or None,
                portal_username or None,
                int(user_id),
                phone,
                username,
                first_name,
                last_name,
                bio,
                display_name,
                geo,
                avatar_path,
                session_name,
                source_type,
                account_status,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _find_account_for_owner(self, user_id: int, portal_user_id: str = "", portal_username: str = "") -> sqlite3.Row | None:
        if portal_user_id or portal_username:
            clauses = []
            args: list[Any] = [int(user_id)]
            if portal_user_id:
                clauses.append("portal_user_id = ?")
                args.append(portal_user_id)
            if portal_username:
                clauses.append("(portal_user_id IS NULL AND portal_username = ?)")
                args.append(portal_username)
            row = self.conn.execute(
                f"SELECT id FROM accounts WHERE user_id = ? AND ({' OR '.join(clauses)}) LIMIT 1",
                tuple(args),
            ).fetchone()
            return row
        return self.conn.execute(
            """
            SELECT id FROM accounts
            WHERE user_id = ?
              AND portal_user_id IS NULL
              AND (portal_username IS NULL OR portal_username = '')
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()

    def list_accounts(self, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        if portal_user_id or portal_username:
            clauses = []
            args: list[Any] = []
            if portal_user_id:
                clauses.append("portal_user_id = ?")
                args.append(portal_user_id)
            if portal_username:
                clauses.append("(portal_user_id IS NULL AND portal_username = ?)")
                args.append(portal_username)
            rows = self.conn.execute(
                f"SELECT * FROM accounts WHERE {' OR '.join(clauses)} ORDER BY id DESC",
                tuple(args),
            ).fetchall()
            return [dict(row) for row in rows]
        rows = self.conn.execute("SELECT * FROM accounts ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    def get_account(self, account_id: int, portal_user_id: str = "", portal_username: str = "") -> dict | None:
        if portal_user_id or portal_username:
            clauses = []
            args: list[Any] = [int(account_id)]
            if portal_user_id:
                clauses.append("portal_user_id = ?")
                args.append(portal_user_id)
            if portal_username:
                clauses.append("(portal_user_id IS NULL AND portal_username = ?)")
                args.append(portal_username)
            row = self.conn.execute(
                f"SELECT * FROM accounts WHERE id = ? AND ({' OR '.join(clauses)}) LIMIT 1",
                tuple(args),
            ).fetchone()
            return dict(row) if row else None
        row = self.conn.execute("SELECT * FROM accounts WHERE id = ? LIMIT 1", (int(account_id),)).fetchone()
        return dict(row) if row else None

    def list_account_folders(self, account_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT account_id, folder_id, title, channels, peers, created_at, updated_at
            FROM account_folders
            WHERE account_id = ?
            ORDER BY title COLLATE NOCASE
            """,
            (int(account_id),),
        ).fetchall()
        return [dict(row) for row in rows]

    def replace_account_folders(self, account_id: int, folders: list[dict]) -> None:
        now = _utc_now()
        folder_ids = [str(folder["id"]) for folder in folders]
        with self.conn:
            for folder in folders:
                self.conn.execute(
                    """
                    INSERT INTO account_folders(account_id, folder_id, title, channels, peers, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, folder_id) DO UPDATE SET
                        title = excluded.title,
                        channels = excluded.channels,
                        peers = excluded.peers,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(account_id),
                        str(folder["id"]),
                        folder.get("title") or "",
                        int(folder.get("channels") or 0),
                        int(folder.get("peers") or 0),
                        now,
                        now,
                    ),
                )

            if folder_ids:
                placeholders = ",".join(["?"] * len(folder_ids))
                self.conn.execute(
                    f"DELETE FROM account_folders WHERE account_id = ? AND folder_id NOT IN ({placeholders})",
                    (int(account_id), *folder_ids),
                )
            else:
                self.conn.execute("DELETE FROM account_folders WHERE account_id = ?", (int(account_id),))

    def upsert_folder_listener(
        self,
        account_id: int,
        folder_id: str,
        folder_title: str,
        status: str,
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> int:
        now = _utc_now()
        existing = self.get_folder_listener(account_id, folder_id, portal_user_id, portal_username)
        if existing:
            self.conn.execute(
                """
                UPDATE folder_listeners
                SET folder_title = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (folder_title, status, now, int(existing["id"])),
            )
            self.conn.commit()
            return int(existing["id"])

        cur = self.conn.execute(
            """
            INSERT INTO folder_listeners(
                portal_user_id, portal_username, account_id, folder_id, folder_title, status, created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (portal_user_id or None, portal_username or None, int(account_id), str(folder_id), folder_title, status, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_folder_listener_status(
        self,
        account_id: int,
        folder_id: str,
        status: str,
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> None:
        where, args = self._owner_where(portal_user_id, portal_username)
        self.conn.execute(
            f"""
            UPDATE folder_listeners
            SET status = ?, updated_at = ?
            WHERE account_id = ? AND folder_id = ? AND {where}
            """,
            (status, _utc_now(), int(account_id), str(folder_id), *args),
        )
        self.conn.commit()

    def get_folder_listener(
        self,
        account_id: int,
        folder_id: str,
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> dict | None:
        where, args = self._owner_where(portal_user_id, portal_username)
        row = self.conn.execute(
            f"""
            SELECT * FROM folder_listeners
            WHERE account_id = ? AND folder_id = ? AND {where}
            LIMIT 1
            """,
            (int(account_id), str(folder_id), *args),
        ).fetchone()
        return dict(row) if row else None

    def list_running_folder_listeners(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM folder_listeners
            WHERE status = 'running'
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def add_folder_log(
        self,
        log_type: str,
        message: str,
        listener_id: int | None = None,
        portal_user_id: str = "",
        portal_username: str = "",
        event_type: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO folder_parser_logs(portal_user_id, portal_username, listener_id, log_type, event_type, message, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (portal_user_id or None, portal_username or None, listener_id, log_type, event_type or None, message, _utc_now()),
        )
        self.conn.commit()

    def list_folder_logs(self, portal_user_id: str = "", portal_username: str = "", limit: int = 200) -> list[dict]:
        where, args = self._owner_where(portal_user_id, portal_username)
        rows = self.conn.execute(
            f"""
            SELECT id, log_type, event_type, message, created_at
            FROM folder_parser_logs
            WHERE {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*args, int(limit)),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_folder_logs(self, portal_user_id: str = "", portal_username: str = "") -> None:
        where, args = self._owner_where(portal_user_id, portal_username)
        self.conn.execute(f"DELETE FROM folder_parser_logs WHERE {where}", tuple(args))
        self.conn.commit()

    def is_folder_link_processed(self, slug: str, portal_user_id: str = "", portal_username: str = "") -> bool:
        where, args = self._owner_where(portal_user_id, portal_username)
        row = self.conn.execute(
            f"""
            SELECT id FROM processed_folder_links
            WHERE addlist_slug = ? AND {where}
            LIMIT 1
            """,
            (slug, *args),
        ).fetchone()
        return row is not None

    def start_folder_link_processing(
        self,
        slug: str,
        link_url: str,
        first_channel_id: int | None = None,
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> bool:
        now = _utc_now()
        try:
            self.conn.execute(
                """
                INSERT INTO processed_folder_links(
                    portal_user_id, portal_username, addlist_slug, link_url, first_channel_id, status, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, 'processing', ?, ?)
                """,
                (portal_user_id or None, portal_username or None, slug, link_url, first_channel_id, now, now),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            where, args = self._owner_where(portal_user_id, portal_username)
            row = self.conn.execute(
                f"""
                SELECT status FROM processed_folder_links
                WHERE addlist_slug = ? AND {where}
                LIMIT 1
                """,
                (slug, *args),
            ).fetchone()
            if row and str(row["status"] or "") in {"failed", "partial"}:
                self.conn.execute(
                    f"""
                    UPDATE processed_folder_links
                    SET link_url = ?, first_channel_id = ?, status = 'processing', updated_at = ?
                    WHERE addlist_slug = ? AND {where}
                    """,
                    (link_url, first_channel_id, now, slug, *args),
                )
                self.conn.commit()
                return True
            return False

    def finish_folder_link_processing(
        self,
        slug: str,
        channels_count: int,
        status: str = "done",
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> None:
        where, args = self._owner_where(portal_user_id, portal_username)
        self.conn.execute(
            f"""
            UPDATE processed_folder_links
            SET channels_count = ?, status = ?, updated_at = ?
            WHERE addlist_slug = ? AND {where}
            """,
            (int(channels_count), status, _utc_now(), slug, *args),
        )
        self.conn.commit()

    def ensure_channel_table(self, portal_user_id: str = "", portal_username: str = "") -> int:
        now = _utc_now()
        where, args = self._channel_table_owner_where(portal_user_id, portal_username)
        row = self.conn.execute(
            f"SELECT id FROM channel_tables WHERE {where} LIMIT 1",
            tuple(args),
        ).fetchone()
        if row:
            table_id = int(row["id"])
            self._ensure_channel_table_access(table_id, portal_user_id, portal_username, "owner")
            return table_id

        title = "Моя таблица"
        cur = self.conn.execute(
            """
            INSERT INTO channel_tables(owner_portal_user_id, owner_portal_username, title, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (portal_user_id or None, portal_username or None, title, now, now),
        )
        table_id = int(cur.lastrowid)
        self._ensure_channel_table_access(table_id, portal_user_id, portal_username, "owner")
        self.conn.commit()
        return table_id

    def list_channel_tables(self, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        self.ensure_channel_table(portal_user_id, portal_username)
        rows = self.conn.execute(
            """
            SELECT DISTINCT
                channel_tables.*,
                CASE
                    WHEN (
                        (channel_tables.owner_portal_user_id IS NOT NULL AND channel_tables.owner_portal_user_id = ?)
                        OR (
                            channel_tables.owner_portal_user_id IS NULL
                            AND channel_tables.owner_portal_username = ?
                        )
                    ) THEN 'owner'
                    ELSE COALESCE(channel_table_access.role, 'editor')
                END AS access_role
            FROM channel_tables
            LEFT JOIN channel_table_access
              ON channel_table_access.table_id = channel_tables.id
            WHERE (
                (channel_tables.owner_portal_user_id IS NOT NULL AND channel_tables.owner_portal_user_id = ?)
                OR (
                    channel_tables.owner_portal_user_id IS NULL
                    AND channel_tables.owner_portal_username = ?
                )
                OR (channel_table_access.portal_user_id IS NOT NULL AND channel_table_access.portal_user_id = ?)
                OR (
                    channel_table_access.portal_user_id IS NULL
                    AND channel_table_access.portal_username = ?
                )
            )
            ORDER BY access_role DESC, channel_tables.id ASC
            """,
            (portal_user_id, portal_username, portal_user_id, portal_username, portal_user_id, portal_username),
        ).fetchall()
        return [self._channel_table_row_to_dict(row, portal_user_id, portal_username) for row in rows]

    def get_accessible_channel_table(self, table_id: int | None, portal_user_id: str = "", portal_username: str = "") -> dict | None:
        if table_id is None:
            table_id = self.ensure_channel_table(portal_user_id, portal_username)
        for table in self.list_channel_tables(portal_user_id, portal_username):
            if int(table["id"]) == int(table_id):
                return table
        return None

    def list_channel_table_access(self, table_id: int, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        table = self.get_accessible_channel_table(table_id, portal_user_id, portal_username)
        if not table:
            return []
        rows = self.conn.execute(
            """
            SELECT id, table_id, portal_user_id, portal_username, role, created_at
            FROM channel_table_access
            WHERE table_id = ?
            ORDER BY role DESC, portal_username COLLATE NOCASE
            """,
            (int(table_id),),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_channel_table_access(self, table_id: int, username: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        table = self.get_accessible_channel_table(table_id, portal_user_id, portal_username)
        if not table or table.get("access_role") != "owner":
            raise PermissionError("Нет доступа к управлению таблицей")
        username = username.strip().lstrip("@")
        if not username:
            raise ValueError("Укажите username пользователя")
        if username.lower() == str(table.get("owner_portal_username") or "").lower():
            role = "owner"
        else:
            role = "editor"
        self._ensure_channel_table_access(int(table_id), "", username, role)
        self.conn.commit()
        return {"portal_user_id": "", "portal_username": username, "role": role}

    def remove_channel_table_access(self, table_id: int, username: str, portal_user_id: str = "", portal_username: str = "") -> None:
        table = self.get_accessible_channel_table(table_id, portal_user_id, portal_username)
        if not table or table.get("access_role") != "owner":
            raise PermissionError("Нет доступа к управлению таблицей")
        username = username.strip().lstrip("@")
        if not username:
            return
        if username.lower() == str(table.get("owner_portal_username") or "").lower():
            raise ValueError("Владельца таблицы удалить нельзя")
        self.conn.execute(
            """
            DELETE FROM channel_table_access
            WHERE table_id = ?
              AND portal_user_id IS NULL
              AND portal_username = ?
              AND role != 'owner'
            """,
            (int(table_id), username),
        )
        self.conn.commit()

    def _ensure_channel_table_access(self, table_id: int, portal_user_id: str = "", portal_username: str = "", role: str = "editor") -> None:
        try:
            self.conn.execute(
                """
                INSERT INTO channel_table_access(table_id, portal_user_id, portal_username, role, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (int(table_id), portal_user_id or None, portal_username or None, role, _utc_now()),
            )
        except sqlite3.IntegrityError:
            self.conn.execute(
                """
                UPDATE channel_table_access
                SET role = ?
                WHERE table_id = ?
                  AND COALESCE(portal_user_id, '') = ?
                  AND COALESCE(portal_username, '') = ?
                """,
                (role, int(table_id), portal_user_id or "", portal_username or ""),
            )

    def _channel_table_row_to_dict(self, row: sqlite3.Row, portal_user_id: str = "", portal_username: str = "") -> dict:
        item = dict(row)
        owner_username = item.get("owner_portal_username") or ""
        owner_user_id = item.get("owner_portal_user_id") or ""
        is_owner = bool((portal_user_id and portal_user_id == owner_user_id) or (not owner_user_id and portal_username and portal_username == owner_username))
        item["is_owner"] = is_owner
        if is_owner:
            item["title"] = item.get("title") or "Моя таблица"
        else:
            item["title"] = f"Таблица @{owner_username}" if owner_username else f"Таблица {owner_user_id or item['id']}"
        return item

    def _channel_table_owner_where(self, portal_user_id: str = "", portal_username: str = "") -> tuple[str, list[Any]]:
        if portal_user_id:
            return "owner_portal_user_id = ?", [portal_user_id]
        if portal_username:
            return "owner_portal_user_id IS NULL AND owner_portal_username = ?", [portal_username]
        return "owner_portal_user_id IS NULL AND (owner_portal_username IS NULL OR owner_portal_username = '')", []

    def upsert_folder_channel(
        self,
        channel_id: int,
        title: str,
        username: str = "",
        link: str = "",
        avatar_path: str = "",
        subscribers: int = 0,
        avg_views_10: int = 0,
        source_channels: list[dict] | None = None,
        account_id: int | None = None,
        folder_id: str = "",
        portal_user_id: str = "",
        portal_username: str = "",
        table_id: int | None = None,
    ) -> int | None:
        table_id = int(table_id or self.ensure_channel_table(portal_user_id, portal_username))
        if self.get_folder_channel_review_status(channel_id, table_id) == "rejected":
            return None

        now = _utc_now()
        existing = self.conn.execute(
            "SELECT * FROM folder_channels WHERE channel_id = ? AND table_id = ? LIMIT 1",
            (int(channel_id), table_id),
        ).fetchone()

        merged_sources = self._merge_folder_sources(
            json.loads(existing["source_channels_json"] or "[]") if existing else [],
            source_channels or [],
        )
        sources_json = json.dumps(merged_sources, ensure_ascii=False)
        source_count = len(merged_sources)

        if existing:
            self.conn.execute(
                """
                UPDATE folder_channels
                SET table_id = ?,
                    account_id = COALESCE(?, account_id),
                    folder_id = COALESCE(?, folder_id),
                    username = ?,
                    title = ?,
                    link = ?,
                    avatar_path = COALESCE(NULLIF(?, ''), avatar_path),
                    subscribers = ?,
                    avg_views_10 = ?,
                    source_count = ?,
                    source_channels_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    table_id,
                    int(account_id) if account_id is not None else None,
                    str(folder_id) if folder_id else None,
                    username,
                    title,
                    link,
                    avatar_path,
                    int(subscribers or 0),
                    int(avg_views_10 or 0),
                    source_count,
                    sources_json,
                    now,
                    int(existing["id"]),
                ),
            )
            self.conn.commit()
            return int(existing["id"])

        cur = self.conn.execute(
            """
            INSERT INTO folder_channels(
                table_id, portal_user_id, portal_username, channel_id, account_id, folder_id, username, title, link,
                avatar_path, subscribers, avg_views_10, source_count, source_channels_json, review_status,
                created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unchecked', ?, ?)
            """,
            (
                table_id,
                portal_user_id or None,
                portal_username or None,
                int(channel_id),
                int(account_id) if account_id is not None else None,
                str(folder_id) if folder_id else None,
                username,
                title,
                link,
                avatar_path,
                int(subscribers or 0),
                int(avg_views_10 or 0),
                source_count,
                sources_json,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_folder_channel_review_status(self, channel_id: int, table_id: int) -> str:
        row = self.conn.execute(
            "SELECT review_status FROM folder_channels WHERE channel_id = ? AND table_id = ? LIMIT 1",
            (int(channel_id), int(table_id)),
        ).fetchone()
        return str(row["review_status"]) if row else ""

    def list_folder_channels(
        self,
        account_id: int | None = None,
        folder_id: str = "",
        include_rejected: bool = True,
        portal_user_id: str = "",
        portal_username: str = "",
        table_id: int | None = None,
    ) -> list[dict]:
        table_id = int(table_id or self.ensure_channel_table(portal_user_id, portal_username))
        clauses = ["table_id = ?"]
        query_args: list[Any] = [table_id]
        if account_id is not None:
            clauses.append("account_id = ?")
            query_args.append(int(account_id))
        if folder_id:
            clauses.append("folder_id = ?")
            query_args.append(str(folder_id))
        if not include_rejected:
            clauses.append("review_status != 'rejected'")

        rows = self.conn.execute(
            f"""
            SELECT * FROM folder_channels
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, id DESC
            """,
            tuple(query_args),
        ).fetchall()
        return [self._folder_channel_row_to_dict(row) for row in rows]

    def set_folder_channel_review_status(
        self,
        channel_id: int,
        review_status: str,
        table_id: int,
    ) -> None:
        self.conn.execute(
            """
            UPDATE folder_channels
            SET review_status = ?, updated_at = ?
            WHERE channel_id = ? AND table_id = ?
            """,
            (review_status, _utc_now(), int(channel_id), int(table_id)),
        )
        self.conn.commit()

    def unlink_stale_folder_channels(
        self,
        account_id: int,
        folder_id: str,
        keep_channel_ids: set[int],
        portal_user_id: str = "",
        portal_username: str = "",
        table_id: int | None = None,
    ) -> int:
        table_id = int(table_id or self.ensure_channel_table(portal_user_id, portal_username))
        query_args: list[Any] = [int(account_id), str(folder_id), table_id]
        keep_clause = ""
        if keep_channel_ids:
            placeholders = ",".join(["?"] * len(keep_channel_ids))
            keep_clause = f" AND channel_id NOT IN ({placeholders})"
            query_args.extend(sorted(int(channel_id) for channel_id in keep_channel_ids))

        cur = self.conn.execute(
            f"""
            UPDATE folder_channels
            SET account_id = NULL,
                folder_id = NULL,
                updated_at = ?
            WHERE account_id = ?
              AND folder_id = ?
              AND table_id = ?
              {keep_clause}
            """,
            (_utc_now(), *query_args),
        )
        self.conn.commit()
        return int(cur.rowcount or 0)

    def delete_folder_channels(self, channel_ids: list[int], table_id: int) -> int:
        if not channel_ids:
            return 0
        placeholders = ",".join(["?"] * len(channel_ids))
        cur = self.conn.execute(
            f"""
            DELETE FROM folder_channels
            WHERE channel_id IN ({placeholders}) AND table_id = ?
            """,
            (*[int(channel_id) for channel_id in channel_ids], int(table_id)),
        )
        self.conn.commit()
        return int(cur.rowcount or 0)

    def _folder_channel_row_to_dict(self, row: sqlite3.Row) -> dict:
        item = dict(row)
        try:
            item["source_channels"] = json.loads(item.get("source_channels_json") or "[]")
        except Exception:
            item["source_channels"] = []
        return item

    def _merge_folder_sources(self, current: list[dict], incoming: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        for source in [*current, *incoming]:
            source_id = str(source.get("id") or "")
            if not source_id:
                continue
            merged[source_id] = {
                "id": source_id,
                "title": source.get("title") or source_id,
                "avatar_url": source.get("avatar_url") or "",
            }
        return list(merged.values())

    def _owner_where(self, portal_user_id: str = "", portal_username: str = "") -> tuple[str, list[Any]]:
        if portal_user_id:
            return "portal_user_id = ?", [portal_user_id]
        if portal_username:
            return "portal_user_id IS NULL AND portal_username = ?", [portal_username]
        return "portal_user_id IS NULL AND (portal_username IS NULL OR portal_username = '')", []


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
