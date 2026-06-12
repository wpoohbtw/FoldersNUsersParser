from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.functions.users import GetFullUserRequest

try:
    import phonenumbers
except Exception:  # pragma: no cover
    phonenumbers = None

from .config import Settings
from .db import Database


@dataclass(slots=True)
class PhoneFlow:
    flow_id: str
    job_id: str
    item_id: str
    phone: str
    portal_user_id: str
    portal_username: str
    session_base: Path
    client: TelegramClient
    phone_code_hash: str


class ImportService:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self._phone_flows: dict[str, PhoneFlow] = {}
        self._bg_tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()

    def list_accounts(self, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        items: list[dict] = []
        for row in self.db.list_accounts(portal_user_id=portal_user_id, portal_username=portal_username):
            avatar_path = row.get("avatar_path") or ""
            items.append(
                {
                    "account_id": row["id"],
                    "user_id": int(row["user_id"]),
                    "phone": row.get("phone") or "",
                    "username": row.get("username") or "",
                    "first_name": row.get("first_name") or "",
                    "last_name": row.get("last_name") or "",
                    "bio": row.get("bio") or "",
                    "display_name": row.get("display_name") or "",
                    "geo": row.get("geo") or self._geo_from_phone(row.get("phone") or ""),
                    "avatar_url": f"/media/avatars/{avatar_path}" if avatar_path else "",
                    "session_name": row.get("session_name") or "",
                    "source_type": row.get("source_type") or "session",
                    "portal_user_id": row.get("portal_user_id") or "",
                    "portal_username": row.get("portal_username") or "",
                    "account_status": row.get("account_status") or "valid",
                    "checked_at": row.get("checked_at") or "",
                    "created_at": row.get("created_at") or "",
                    "roles": [],
                }
            )
        return items

    async def import_session_files(self, files: list[Path], portal_user_id: str = "", portal_username: str = "") -> str:
        self._ensure_api_configured()
        job_id = f"job_{uuid4().hex[:12]}"
        self.db.create_job(
            job_id=job_id,
            import_type="session",
            total=len(files),
            status="running",
            portal_user_id=portal_user_id,
            portal_username=portal_username,
        )
        self._spawn_bg_task(self._run_session_job(job_id, files))
        return job_id

    async def start_phone_import(self, phone: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        self._ensure_api_configured()
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            raise ValueError("Введите номер телефона в международном формате")

        flow_id = f"phf_{uuid4().hex[:12]}"
        job_id = f"job_{uuid4().hex[:12]}"
        item_id = f"itm_{uuid4().hex[:12]}"
        session_name = f"phone_{_digits(clean_phone)}_{uuid4().hex[:8]}"
        session_base = self.settings.sessions_dir / session_name

        client = TelegramClient(str(session_base), self.settings.api_id, self.settings.api_hash)
        await client.connect()
        try:
            sent = await client.send_code_request(clean_phone)
        except PhoneNumberInvalidError:
            await client.disconnect()
            self._close_session_storage(client)
            raise ValueError("Неверный формат номера")
        except PhoneNumberBannedError:
            await client.disconnect()
            self._close_session_storage(client)
            raise ValueError("Этот номер заблокирован Telegram")
        except PhoneNumberFloodError:
            await client.disconnect()
            self._close_session_storage(client)
            raise ValueError("Слишком много попыток. Попробуйте позже")
        except Exception:
            await client.disconnect()
            self._close_session_storage(client)
            raise ValueError("Не удалось отправить код. Попробуйте позже")

        self.db.create_job(
            job_id=job_id,
            import_type="phone",
            total=1,
            status="running",
            portal_user_id=portal_user_id,
            portal_username=portal_username,
        )
        self.db.create_item(item_id=item_id, job_id=job_id, filename=clean_phone, status="processing", source_type="phone", file_format="phone")

        flow = PhoneFlow(
            flow_id=flow_id,
            job_id=job_id,
            item_id=item_id,
            phone=clean_phone,
            portal_user_id=portal_user_id,
            portal_username=portal_username,
            session_base=session_base,
            client=client,
            phone_code_hash=sent.phone_code_hash,
        )
        async with self._lock:
            self._phone_flows[flow_id] = flow

        return {"flow_id": flow_id, "job_id": job_id, "next_step": "code"}

    async def submit_phone_code(self, flow_id: str, code: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        flow = await self._get_flow(flow_id, portal_user_id=portal_user_id, portal_username=portal_username)
        try:
            await flow.client.sign_in(
                phone=flow.phone,
                code=code.strip(),
                phone_code_hash=flow.phone_code_hash,
            )
            result = await self._finalize_phone_flow(flow)
            return {"next_step": "done", **result}
        except SessionPasswordNeededError:
            return {"next_step": "password", "flow_id": flow.flow_id, "job_id": flow.job_id}
        except PhoneCodeInvalidError:
            raise ValueError("Неверный код. Проверьте и попробуйте снова")
        except PhoneCodeExpiredError:
            await self._fail_phone_flow(flow, "Код подтверждения истек")
            raise ValueError("Код истек. Начните вход заново")
        except PhoneCodeEmptyError:
            raise ValueError("Введите код из Telegram")
        except Exception:
            await self._fail_phone_flow(flow, "Ошибка подтверждения кода")
            raise ValueError("Не удалось подтвердить код. Начните вход заново")

    async def submit_phone_password(self, flow_id: str, password: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        flow = await self._get_flow(flow_id, portal_user_id=portal_user_id, portal_username=portal_username)
        try:
            await flow.client.sign_in(password=password)
            result = await self._finalize_phone_flow(flow)
            return {"next_step": "done", **result}
        except PasswordHashInvalidError:
            raise ValueError("Неверный пароль 2FA. Попробуйте снова")
        except Exception:
            await self._fail_phone_flow(flow, "Ошибка 2FA пароля")
            raise ValueError("Не удалось завершить вход. Начните заново")

    async def cancel_phone_flow(self, flow_id: str, portal_user_id: str = "", portal_username: str = "") -> None:
        flow = await self._get_flow(flow_id, portal_user_id=portal_user_id, portal_username=portal_username)
        if not flow:
            return
        await self._pop_flow(flow_id)
        await flow.client.disconnect()
        self._close_session_storage(flow.client)
        await self._safe_unlink(_session_file_path(flow.session_base))
        self.db.set_job_status(flow.job_id, "canceled", finished=True)

    def get_job(self, job_id: str, portal_user_id: str = "", portal_username: str = "") -> dict | None:
        row = self.db.get_job(job_id)
        if not row:
            return None
        if not self._owner_matches(row, portal_user_id, portal_username):
            return None
        return {
            "job_id": row["id"],
            "portal_user_id": row.get("portal_user_id") or "",
            "portal_username": row.get("portal_username") or "",
            "type": row["import_type"],
            "status": row["status"],
            "total": int(row["total"]),
            "success": int(row["success"]),
            "failed": int(row["failed"]),
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }

    def get_job_items(self, job_id: str, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        if not self.get_job(job_id, portal_user_id=portal_user_id, portal_username=portal_username):
            return []
        items: list[dict] = []
        for row in self.db.list_items(job_id):
            avatar_path = row.get("avatar_path") or ""
            items.append(
                {
                    "item_id": row["id"],
                    "filename": row["filename"],
                    "status": row["status"],
                    "message": row.get("message") or "",
                    "account_id": row.get("account_id"),
                    "source_type": row.get("source_type") or "",
                    "file_format": row.get("file_format") or "",
                    "user_id": row.get("user_id") or 0,
                    "phone": row.get("phone") or "",
                    "username": row.get("username") or "",
                    "first_name": row.get("first_name") or "",
                    "last_name": row.get("last_name") or "",
                    "bio": row.get("bio") or "",
                    "display_name": row.get("display_name") or "",
                    "geo": row.get("geo") or self._geo_from_phone(row.get("phone") or ""),
                    "avatar_url": f"/media/avatars/{avatar_path}" if avatar_path else "",
                    "staged_session_name": row.get("staged_session_name") or "",
                    "is_saved": bool(row.get("is_saved") or 0),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return items

    async def check_job_items(
        self,
        job_id: str,
        item_ids: list[str] | None = None,
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> dict:
        if not self.get_job(job_id, portal_user_id=portal_user_id, portal_username=portal_username):
            raise ValueError("Job не найден")
        all_items = self.db.list_items(job_id)
        selected = [item for item in all_items if not item_ids or item["id"] in item_ids]
        checked = 0
        failed = 0

        for item in selected:
            staged_session_name = item.get("staged_session_name") or ""
            if not staged_session_name:
                continue
            session_file = self.settings.sessions_dir / f"{staged_session_name}.session"
            if not session_file.exists():
                self.db.update_item(item["id"], "failed", "Файл сессии для проверки не найден")
                failed += 1
                continue

            try:
                profile = await self._read_session_profile(
                    session_file.with_suffix(""),
                    portal_user_id=portal_user_id,
                    portal_username=portal_username,
                )
                self.db.update_item_fields(item["id"], status="checked", message="Проверен", **profile)
                checked += 1
            except Exception as err:
                self.db.update_item(item["id"], "failed", str(err))
                failed += 1

        return {"checked": checked, "failed": failed}

    async def save_job_items(
        self,
        job_id: str,
        item_ids: list[str] | None = None,
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> dict:
        job = self.db.get_job(job_id)
        if not job or not self._owner_matches(job, portal_user_id, portal_username):
            raise ValueError("Job не найден")
        owner_user_id = job.get("portal_user_id") or portal_user_id
        owner_username = job.get("portal_username") or portal_username
        items = self.db.list_unsaved_items(job_id, item_ids)
        saved = 0
        failed = 0

        for item in items:
            staged_session_name = item.get("staged_session_name") or ""
            user_id = int(item.get("user_id") or 0)
            if user_id <= 0 or not staged_session_name:
                self.db.update_item(item["id"], "failed", "Нельзя сохранить: сначала проверьте аккаунт")
                failed += 1
                continue

            staged_file = self.settings.sessions_dir / f"{staged_session_name}.session"
            if not staged_file.exists():
                self.db.update_item(item["id"], "failed", "Файл сессии не найден")
                failed += 1
                continue

            final_session_name = f"{user_id}_{uuid4().hex[:8]}"
            final_file = self.settings.sessions_dir / f"{final_session_name}.session"

            try:
                await self._safe_move_file(staged_file, final_file)
                account_id = self.db.upsert_account(
                    user_id=user_id,
                    phone=item.get("phone") or "",
                    username=item.get("username") or "",
                    first_name=item.get("first_name") or "",
                    last_name=item.get("last_name") or "",
                    bio=item.get("bio") or "",
                    display_name=item.get("display_name") or "",
                    geo=item.get("geo") or self._geo_from_phone(item.get("phone") or ""),
                    avatar_path=item.get("avatar_path") or "",
                    session_name=final_session_name,
                    source_type=item.get("source_type") or "session",
                    account_status="valid",
                    portal_user_id=owner_user_id,
                    portal_username=owner_username,
                )
                self.db.update_item_fields(
                    item["id"],
                    status="saved",
                    message="Сохранено",
                    account_id=account_id,
                    is_saved=1,
                    staged_session_name="",
                )
                saved += 1
            except Exception as err:
                self.db.update_item(item["id"], "failed", f"Ошибка сохранения: {err}")
                failed += 1

        return {"saved": saved, "failed": failed}

    async def check_accounts(self, account_ids: list[int], portal_user_id: str = "", portal_username: str = "") -> dict:
        checked = 0
        failed = 0
        for account_id in account_ids:
            account = self.db.get_account(int(account_id), portal_user_id=portal_user_id, portal_username=portal_username)
            if not account:
                failed += 1
                continue

            session_name = account.get("session_name") or ""
            session_file = self.settings.sessions_dir / f"{session_name}.session"
            if not session_file.exists():
                self._mark_account_invalid(account)
                failed += 1
                continue

            try:
                profile = await self._read_session_profile(
                    session_file.with_suffix(""),
                    portal_user_id=account.get("portal_user_id") or portal_user_id,
                    portal_username=account.get("portal_username") or portal_username,
                )
                self.db.upsert_account(
                    user_id=profile["user_id"],
                    phone=profile["phone"],
                    username=profile["username"],
                    first_name=profile["first_name"],
                    last_name=profile["last_name"],
                    bio=profile["bio"],
                    display_name=profile["display_name"],
                    geo=profile["geo"],
                    avatar_path=profile["avatar_path"] or account.get("avatar_path") or "",
                    session_name=session_name,
                    source_type=account.get("source_type") or "session",
                    account_status="valid",
                    portal_user_id=account.get("portal_user_id") or portal_user_id,
                    portal_username=account.get("portal_username") or portal_username,
                )
                checked += 1
            except Exception:
                self._mark_account_invalid(account)
                failed += 1

        return {"checked": checked, "failed": failed}

    async def list_account_folders(self, account_id: int, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        account = self.db.get_account(int(account_id), portal_user_id=portal_user_id, portal_username=portal_username)
        if not account:
            raise ValueError("Аккаунт не найден")

        session_name = account.get("session_name") or ""
        session_file = self.settings.sessions_dir / f"{session_name}.session"
        if not session_file.exists():
            raise ValueError("Файл сессии аккаунта не найден")

        client = TelegramClient(str(session_file.with_suffix("")), self.settings.api_id, self.settings.api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError("Сессия аккаунта не авторизована")

            result = await client(GetDialogFiltersRequest())
            filters = getattr(result, "filters", result) or []
            folders: list[dict] = []
            for folder_filter in filters:
                folder_id = getattr(folder_filter, "id", None)
                if folder_id is None:
                    continue

                include_peers = list(getattr(folder_filter, "include_peers", []) or [])
                pinned_peers = list(getattr(folder_filter, "pinned_peers", []) or [])
                exclude_peers = list(getattr(folder_filter, "exclude_peers", []) or [])
                excluded_ids = {
                    int(getattr(peer, "channel_id", 0) or 0)
                    for peer in exclude_peers
                    if int(getattr(peer, "channel_id", 0) or 0) > 0
                }
                channel_ids = {
                    int(getattr(peer, "channel_id", 0) or 0)
                    for peer in [*include_peers, *pinned_peers]
                    if peer.__class__.__name__ in {"InputPeerChannel", "InputPeerChannelFromMessage"}
                    and int(getattr(peer, "channel_id", 0) or 0) > 0
                    and int(getattr(peer, "channel_id", 0) or 0) not in excluded_ids
                }
                title = self._dialog_filter_title(folder_filter)
                if not title:
                    continue

                folders.append(
                    {
                        "id": str(folder_id),
                        "title": title,
                        "channels": len(channel_ids),
                        "peers": len(include_peers),
                    }
                )
            self.db.replace_account_folders(int(account["id"]), folders)
            return folders
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
            self._close_session_storage(client)

    def list_saved_account_folders(self, account_id: int, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        account = self.db.get_account(int(account_id), portal_user_id=portal_user_id, portal_username=portal_username)
        if not account:
            raise ValueError("Аккаунт не найден")

        return [
            {
                "id": row["folder_id"],
                "title": row["title"],
                "channels": int(row["channels"]),
                "peers": int(row["peers"]),
                "updated_at": row["updated_at"],
            }
            for row in self.db.list_account_folders(int(account["id"]))
        ]

    async def _run_session_job(self, job_id: str, files: list[Path]) -> None:
        success = 0
        failed = 0
        job = self.db.get_job(job_id) or {}
        portal_user_id = job.get("portal_user_id") or ""
        portal_username = job.get("portal_username") or ""
        try:
            for file_path in files:
                item_id = f"itm_{uuid4().hex[:12]}"
                self.db.create_item(item_id, job_id, file_path.name, "processing", source_type="session", file_format=".session")
                try:
                    staged_session_name = await self._validate_and_stage_session(
                        file_path,
                        portal_user_id=portal_user_id,
                        portal_username=portal_username,
                    )
                    self.db.update_item_fields(
                        item_id,
                        status="done",
                        message="Импортировано. Нажмите Проверить аккаунты",
                        staged_session_name=staged_session_name,
                    )
                    success += 1
                    self.db.increment_job_counts(job_id, success_inc=1)
                except Exception as err:
                    failed += 1
                    self.db.update_item(item_id, "failed", str(err))
                    self.db.increment_job_counts(job_id, failed_inc=1)
                finally:
                    await self._safe_unlink(file_path)

            status = "done" if failed == 0 else ("failed" if success == 0 else "partial_done")
            self.db.set_job_status(job_id, status, finished=True)
        except Exception as err:
            self.db.set_job_status(job_id, "failed", finished=True)
            fallback_item_id = f"itm_{uuid4().hex[:12]}"
            self.db.create_item(fallback_item_id, job_id, "system", "failed", source_type="session", file_format="system")
            self.db.update_item(fallback_item_id, "failed", f"Системная ошибка импорта: {err}")
            self.db.increment_job_counts(job_id, failed_inc=max(1, len(files)))

    async def _validate_and_stage_session(self, source_file: Path, portal_user_id: str = "", portal_username: str = "") -> str:
        base_name = f"imp_{uuid4().hex[:12]}"
        target_file = self.settings.sessions_dir / f"{base_name}.session"
        shutil.copy2(source_file, target_file)

        session_base = target_file.with_suffix("")
        moved = False
        client = TelegramClient(str(session_base), self.settings.api_id, self.settings.api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError(
                    "Сессия не авторизована для текущего API_ID/API_HASH или это не Telethon-session"
                )

            staged_session_name = f"stg_{uuid4().hex[:16]}"
            staged_file = self.settings.sessions_dir / f"{staged_session_name}.session"
            await client.disconnect()
            self._close_session_storage(client)
            await self._safe_move_file(target_file, staged_file)
            moved = True
            return staged_session_name
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
            self._close_session_storage(client)
            if not moved:
                await self._safe_unlink(target_file)

    async def _read_session_profile(self, session_base: Path, portal_user_id: str = "", portal_username: str = "") -> dict:
        client = TelegramClient(str(session_base), self.settings.api_id, self.settings.api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError("Сессия не авторизована")

            me = await client.get_me()
            if me is None:
                raise ValueError("Не удалось прочитать профиль")

            user_id = int(getattr(me, "id", 0) or 0)
            if user_id <= 0:
                raise ValueError("Некорректный user_id")

            phone = getattr(me, "phone", "") or ""
            username = getattr(me, "username", "") or ""
            first_name = getattr(me, "first_name", "") or ""
            last_name = getattr(me, "last_name", "") or ""
            normalized_phone = self._normalize_phone(phone)
            bio = await self._read_about(client)
            display_name = (f"{first_name} {last_name}").strip() or (f"@{username}" if username else f"user_{user_id}")
            avatar_path = await self._download_avatar(
                client,
                user_id,
                portal_user_id=portal_user_id,
                portal_username=portal_username,
            )

            return {
                "user_id": user_id,
                "phone": normalized_phone,
                "username": f"@{username}" if username else "",
                "first_name": first_name,
                "last_name": last_name,
                "bio": bio,
                "display_name": display_name,
                "geo": self._geo_from_phone(normalized_phone),
                "avatar_path": avatar_path,
            }
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
            self._close_session_storage(client)

    async def _read_about(self, client: TelegramClient) -> str:
        try:
            full = await client(GetFullUserRequest("me"))
            return str(getattr(getattr(full, "full_user", None), "about", "") or "")
        except Exception:
            return ""

    async def _finalize_phone_flow(self, flow: PhoneFlow) -> dict:
        profile = await self._read_live_profile(flow.client, flow.phone)
        avatar_path = await self._download_avatar(
            flow.client,
            int(profile["user_id"]),
            portal_user_id=flow.portal_user_id,
            portal_username=flow.portal_username,
        )

        staged_session_name = f"stg_{uuid4().hex[:16]}"
        staged_file = self.settings.sessions_dir / f"{staged_session_name}.session"
        session_file = _session_file_path(flow.session_base)

        await flow.client.disconnect()
        self._close_session_storage(flow.client)

        if not session_file.exists():
            await self._fail_phone_flow(flow, "Файл сессии не создан")
            raise ValueError("Файл сессии не создан")

        await self._safe_move_file(session_file, staged_file)
        async with self._lock:
            self._phone_flows.pop(flow.flow_id, None)

        self.db.update_item_fields(
            flow.item_id,
            status="checked",
            message="Проверен",
            user_id=profile["user_id"],
            phone=profile["phone"],
            username=profile["username"],
            first_name=profile["first_name"],
            last_name=profile["last_name"],
            bio=profile["bio"],
            display_name=profile["display_name"],
            geo=profile["geo"],
            avatar_path=avatar_path,
            staged_session_name=staged_session_name,
        )
        self.db.increment_job_counts(flow.job_id, success_inc=1)
        self.db.set_job_status(flow.job_id, "done", finished=True)

        return {"job_id": flow.job_id, "item_id": flow.item_id}

    async def _read_live_profile(self, client: TelegramClient, fallback_phone: str = "") -> dict:
        me = await client.get_me()
        if me is None:
            raise ValueError("Не удалось прочитать профиль")

        user_id = int(getattr(me, "id", 0) or 0)
        if user_id <= 0:
            raise ValueError("Некорректный user_id")

        phone = getattr(me, "phone", "") or fallback_phone
        username = getattr(me, "username", "") or ""
        first_name = getattr(me, "first_name", "") or ""
        last_name = getattr(me, "last_name", "") or ""
        normalized_phone = self._normalize_phone(phone)
        bio = await self._read_about(client)
        display_name = (f"{first_name} {last_name}").strip() or (f"@{username}" if username else f"user_{user_id}")

        return {
            "user_id": user_id,
            "phone": normalized_phone,
            "username": f"@{username}" if username else "",
            "first_name": first_name,
            "last_name": last_name,
            "bio": bio,
            "display_name": display_name,
            "geo": self._geo_from_phone(normalized_phone),
        }

    async def _download_avatar(
        self,
        client: TelegramClient,
        user_id: int,
        portal_user_id: str = "",
        portal_username: str = "",
    ) -> str:
        owner_segment = self._owner_storage_segment(portal_user_id=portal_user_id, portal_username=portal_username)
        avatar_dir = self.settings.avatars_dir / owner_segment
        avatar_dir.mkdir(parents=True, exist_ok=True)
        avatar_name = f"{user_id}.jpg"
        avatar_path = avatar_dir / avatar_name
        try:
            await client.download_profile_photo("me", file=str(avatar_path), download_big=False)
            if avatar_path.exists() and avatar_path.stat().st_size > 0:
                return f"{owner_segment}/{avatar_name}"
        except Exception:
            return ""
        return ""

    def _owner_storage_segment(self, portal_user_id: str = "", portal_username: str = "") -> str:
        raw = portal_user_id or portal_username or "anonymous"
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw).strip("._-")
        return safe or "anonymous"

    def _mark_account_invalid(self, account: dict[str, Any]) -> None:
        self.db.upsert_account(
            user_id=int(account["user_id"]),
            phone=account.get("phone") or "",
            username=account.get("username") or "",
            first_name=account.get("first_name") or "",
            last_name=account.get("last_name") or "",
            bio=account.get("bio") or "",
            display_name=account.get("display_name") or "",
            geo=account.get("geo") or "",
            avatar_path=account.get("avatar_path") or "",
            session_name=account.get("session_name") or "",
            source_type=account.get("source_type") or "session",
            account_status="invalid",
            portal_user_id=account.get("portal_user_id") or "",
            portal_username=account.get("portal_username") or "",
        )

    def _dialog_filter_title(self, folder_filter: Any) -> str:
        raw_title = getattr(folder_filter, "title", "")
        if isinstance(raw_title, str):
            return raw_title.strip()
        text = getattr(raw_title, "text", "")
        if isinstance(text, str):
            return text.strip()
        return str(raw_title or "").strip()

    def _owner_matches(self, row: dict[str, Any], portal_user_id: str = "", portal_username: str = "") -> bool:
        row_user_id = row.get("portal_user_id") or ""
        row_username = row.get("portal_username") or ""
        if not row_user_id and not row_username:
            return True
        if portal_user_id and row_user_id == portal_user_id:
            return True
        return bool(portal_username and not row_user_id and row_username == portal_username)

    def _flow_owner_matches(self, flow: PhoneFlow, portal_user_id: str = "", portal_username: str = "") -> bool:
        return self._owner_matches(
            {"portal_user_id": flow.portal_user_id, "portal_username": flow.portal_username},
            portal_user_id=portal_user_id,
            portal_username=portal_username,
        )

    def _ensure_api_configured(self) -> None:
        if self.settings.api_id <= 0 or not self.settings.api_hash:
            raise ValueError("Укажите API_ID и API_HASH в .env")

    async def _get_flow(self, flow_id: str, portal_user_id: str = "", portal_username: str = "") -> PhoneFlow:
        async with self._lock:
            flow = self._phone_flows.get(flow_id)
        if not flow or not self._flow_owner_matches(flow, portal_user_id=portal_user_id, portal_username=portal_username):
            raise ValueError("Сессия авторизации не найдена. Начните вход заново")
        return flow

    async def _pop_flow(self, flow_id: str) -> PhoneFlow | None:
        async with self._lock:
            return self._phone_flows.pop(flow_id, None)

    async def _fail_phone_flow(self, flow: PhoneFlow, message: str) -> None:
        await self._pop_flow(flow.flow_id)
        try:
            await flow.client.disconnect()
        except Exception:
            pass
        self._close_session_storage(flow.client)
        await self._safe_unlink(_session_file_path(flow.session_base))
        self.db.update_item(flow.item_id, "failed", message)
        self.db.increment_job_counts(flow.job_id, failed_inc=1)
        self.db.set_job_status(flow.job_id, "failed", finished=True)

    def _normalize_phone(self, phone: str) -> str:
        raw = (phone or "").strip()
        if not raw:
            return ""
        compact = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
        if compact.startswith("00"):
            compact = f"+{compact[2:]}"
        elif not compact.startswith("+") and compact.isdigit():
            compact = f"+{compact}"
        digits = compact[1:] if compact.startswith("+") else compact
        if len(digits) < 6 or len(digits) > 15 or not digits.isdigit():
            return ""
        return f"+{digits}"

    def _geo_from_phone(self, phone: str) -> str:
        raw = self._normalize_phone(phone)
        if not raw or phonenumbers is None:
            return ""
        try:
            parsed = phonenumbers.parse(raw, None)
            return (phonenumbers.region_code_for_number(parsed) or "").upper()
        except Exception:
            return ""

    def _spawn_bg_task(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _close_session_storage(self, client: TelegramClient) -> None:
        try:
            session_obj = getattr(client, "session", None)
            if session_obj is not None:
                session_obj.close()
        except Exception:
            pass

    async def _safe_move_file(self, src: Path, dst: Path, retries: int = 6, delay: float = 0.12) -> None:
        last_error: Exception | None = None
        for _ in range(retries):
            try:
                shutil.move(src, dst)
                return
            except PermissionError as err:
                last_error = err
                await asyncio.sleep(delay)
        if last_error:
            raise last_error

    async def _safe_unlink(self, file_path: Path, retries: int = 6, delay: float = 0.12) -> None:
        if not file_path.exists():
            return
        for _ in range(retries):
            try:
                file_path.unlink(missing_ok=True)
                return
            except PermissionError:
                await asyncio.sleep(delay)


def _digits(phone: str) -> str:
    out = "".join(ch for ch in phone if ch.isdigit())
    return out or "account"


def _session_file_path(base_path: Path) -> Path:
    return base_path.with_suffix(".session")
