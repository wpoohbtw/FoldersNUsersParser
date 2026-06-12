from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events
from telethon.errors.rpcerrorlist import UserAlreadyParticipantError
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.tl.functions.chatlists import CheckChatlistInviteRequest, JoinChatlistInviteRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.tl.types import DialogFilter, DialogFilterChatlist, MessageEntityTextUrl, MessageEntityUrl

from .config import Settings
from .db import Database


ADDLIST_RE = re.compile(r"https?://t\.me/addlist/([A-Za-z0-9_-]+)", re.IGNORECASE)


@dataclass(slots=True)
class ActiveFolderListener:
    key: str
    listener_id: int
    portal_user_id: str
    portal_username: str
    account_id: int
    folder_id: str
    folder_title: str
    client: TelegramClient
    task: asyncio.Task
    active_channel_ids: set[int] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class FolderParserService:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self._listeners: dict[str, ActiveFolderListener] = {}
        self._lock = asyncio.Lock()

    async def restore_running_listeners(self) -> None:
        for row in self.db.list_running_folder_listeners():
            account = self.db.get_account(
                int(row["account_id"]),
                portal_user_id=row.get("portal_user_id") or "",
                portal_username=row.get("portal_username") or "",
            )
            if not account:
                self.db.set_folder_listener_status(
                    int(row["account_id"]),
                    str(row["folder_id"]),
                    "idle",
                    portal_user_id=row.get("portal_user_id") or "",
                    portal_username=row.get("portal_username") or "",
                )
                continue
            try:
                await self.start_listener(
                    account,
                    str(row["folder_id"]),
                    portal_user_id=row.get("portal_user_id") or "",
                    portal_username=row.get("portal_username") or "",
                )
            except Exception as err:
                self.db.set_folder_listener_status(
                    int(row["account_id"]),
                    str(row["folder_id"]),
                    "idle",
                    portal_user_id=row.get("portal_user_id") or "",
                    portal_username=row.get("portal_username") or "",
                )
                self.db.add_folder_log(
                    "warn",
                    f"Не удалось восстановить парсер после рестарта: {err}",
                    listener_id=int(row["id"]),
                    portal_user_id=row.get("portal_user_id") or "",
                    portal_username=row.get("portal_username") or "",
                )

    async def sync_folder_once(self, account: dict, folder_id: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        self._ensure_api_configured()
        session_name = account.get("session_name") or ""
        session_file = self.settings.sessions_dir / f"{session_name}.session"
        if not session_file.exists():
            raise ValueError("Файл сессии аккаунта не найден")

        client = TelegramClient(str(session_file.with_suffix("")), self.settings.api_id, self.settings.api_hash)
        task = asyncio.create_task(asyncio.sleep(0))
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError("Сессия аккаунта не авторизована")

            folder_filter = await self._get_folder_filter(client, int(folder_id))
            folder_title = self._dialog_filter_title(folder_filter)
            listener_id = self.db.upsert_folder_listener(
                account_id=int(account["id"]),
                folder_id=str(folder_id),
                folder_title=folder_title,
                status="idle",
                portal_user_id=portal_user_id,
                portal_username=portal_username,
            )
            listener = ActiveFolderListener(
                key="sync-once",
                listener_id=listener_id,
                portal_user_id=portal_user_id,
                portal_username=portal_username,
                account_id=int(account["id"]),
                folder_id=str(folder_id),
                folder_title=folder_title,
                client=client,
                task=task,
            )
            active_ids = await self._sync_folder_channels(listener, folder_filter, source_channel=None)
            return {
                "status": "idle",
                "listener_id": listener_id,
                "account_id": int(account["id"]),
                "folder_id": str(folder_id),
                "folder_title": folder_title,
                "channels": len(active_ids),
            }
        finally:
            if not task.done():
                task.cancel()
            try:
                await client.disconnect()
            except Exception:
                pass
            self._close_session_storage(client)

    async def start_listener(self, account: dict, folder_id: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        self._ensure_api_configured()
        key = self._listener_key(portal_user_id, portal_username, int(account["id"]), str(folder_id))
        async with self._lock:
            if key in self._listeners:
                listener = self._listeners[key]
                return self._listener_payload(listener, "running")

            session_name = account.get("session_name") or ""
            session_file = self.settings.sessions_dir / f"{session_name}.session"
            if not session_file.exists():
                raise ValueError("Файл сессии аккаунта не найден")

            client = TelegramClient(str(session_file.with_suffix("")), self.settings.api_id, self.settings.api_hash)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise ValueError("Сессия аккаунта не авторизована")

            folder_filter = await self._get_folder_filter(client, int(folder_id))
            folder_title = self._dialog_filter_title(folder_filter)
            listener_id = self.db.upsert_folder_listener(
                account_id=int(account["id"]),
                folder_id=str(folder_id),
                folder_title=folder_title,
                status="running",
                portal_user_id=portal_user_id,
                portal_username=portal_username,
            )
            listener = ActiveFolderListener(
                key=key,
                listener_id=listener_id,
                portal_user_id=portal_user_id,
                portal_username=portal_username,
                account_id=int(account["id"]),
                folder_id=str(folder_id),
                folder_title=folder_title,
                client=client,
                task=asyncio.create_task(client.run_until_disconnected()),
            )
            listener.active_channel_ids = await self._sync_folder_channels(listener, folder_filter, source_channel=None)
            client.add_event_handler(self._make_message_handler(listener), events.NewMessage())
            await client.catch_up()
            self._listeners[key] = listener

        self._log(
            listener,
            "system",
            f"Парсер запущен, слушаю {len(listener.active_channel_ids)} каналов",
            event_type="parser-started",
        )
        return self._listener_payload(listener, "running")

    async def stop_listener(self, account_id: int, folder_id: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        key = self._listener_key(portal_user_id, portal_username, int(account_id), str(folder_id))
        async with self._lock:
            listener = self._listeners.pop(key, None)

        if listener:
            self._log(listener, "warn", "Парсер остановлен", event_type="parser-stopped")
            self.db.set_folder_listener_status(
                listener.account_id,
                listener.folder_id,
                "idle",
                portal_user_id=listener.portal_user_id,
                portal_username=listener.portal_username,
            )
            await listener.client.disconnect()
            listener.task.cancel()
            return self._listener_payload(listener, "idle")

        self.db.set_folder_listener_status(
            account_id,
            folder_id,
            "idle",
            portal_user_id=portal_user_id,
            portal_username=portal_username,
        )
        return {"status": "idle", "channels": 0}

    async def stop_all(self) -> None:
        listeners = list(self._listeners.values())
        self._listeners.clear()
        for listener in listeners:
            try:
                await listener.client.disconnect()
            except Exception:
                pass
            listener.task.cancel()

    def get_listener_status(self, account_id: int, folder_id: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        key = self._listener_key(portal_user_id, portal_username, int(account_id), str(folder_id))
        listener = self._listeners.get(key)
        if listener:
            return self._listener_payload(listener, "running")
        row = self.db.get_folder_listener(
            account_id,
            folder_id,
            portal_user_id=portal_user_id,
            portal_username=portal_username,
        )
        if row and row.get("status") == "running":
            self.db.set_folder_listener_status(
                account_id,
                folder_id,
                "idle",
                portal_user_id=portal_user_id,
                portal_username=portal_username,
            )
            return {
                "status": "idle",
                "channels": 0,
            }
        return {
            "status": row.get("status") if row else "idle",
            "channels": 0,
        }

    def get_active_listener(self, portal_user_id: str = "", portal_username: str = "") -> dict:
        owner_prefix = portal_user_id or f"username:{portal_username}" or "anonymous"
        for key, listener in self._listeners.items():
            if key.startswith(f"{owner_prefix}:"):
                return self._listener_payload(listener, "running")
        return {"status": "idle", "channels": 0}

    def list_channels(
        self,
        account_id: int | None = None,
        folder_id: str = "",
        include_rejected: bool = True,
        portal_user_id: str = "",
        portal_username: str = "",
        table_id: int | None = None,
    ) -> list[dict]:
        table = self.db.get_accessible_channel_table(table_id, portal_user_id, portal_username)
        if not table:
            raise PermissionError("Нет доступа к таблице каналов")
        return [
            self._channel_payload(row)
            for row in self.db.list_folder_channels(
                account_id=account_id,
                folder_id=folder_id,
                include_rejected=include_rejected,
                portal_user_id=portal_user_id,
                portal_username=portal_username,
                table_id=int(table["id"]),
            )
        ]

    def list_logs(self, portal_user_id: str = "", portal_username: str = "") -> list[dict]:
        return [
            {
                "id": str(row["id"]),
                "timestamp": row["created_at"],
                "type": row["log_type"],
                "event_type": row.get("event_type") or "",
                "message": row["message"],
            }
            for row in self.db.list_folder_logs(portal_user_id=portal_user_id, portal_username=portal_username)
        ]

    def clear_logs(self, portal_user_id: str = "", portal_username: str = "") -> None:
        self.db.clear_folder_logs(portal_user_id=portal_user_id, portal_username=portal_username)

    def approve_channel(self, channel_id: int, table_id: int, portal_user_id: str = "", portal_username: str = "") -> None:
        self._ensure_table_access(table_id, portal_user_id, portal_username)
        self.db.set_folder_channel_review_status(
            channel_id,
            "checked",
            table_id=table_id,
        )

    def reject_channel(self, channel_id: int, table_id: int, portal_user_id: str = "", portal_username: str = "") -> None:
        self._ensure_table_access(table_id, portal_user_id, portal_username)
        self.db.set_folder_channel_review_status(
            channel_id,
            "rejected",
            table_id=table_id,
        )

    def reset_channel(self, channel_id: int, table_id: int, portal_user_id: str = "", portal_username: str = "") -> None:
        self._ensure_table_access(table_id, portal_user_id, portal_username)
        self.db.set_folder_channel_review_status(
            channel_id,
            "unchecked",
            table_id=table_id,
        )

    def delete_channels(self, channel_ids: list[int], table_id: int, portal_user_id: str = "", portal_username: str = "") -> int:
        self._ensure_table_access(table_id, portal_user_id, portal_username)
        return self.db.delete_folder_channels(
            channel_ids,
            table_id=table_id,
        )

    def _ensure_table_access(self, table_id: int, portal_user_id: str = "", portal_username: str = "") -> dict:
        table = self.db.get_accessible_channel_table(table_id, portal_user_id, portal_username)
        if not table:
            raise PermissionError("Нет доступа к таблице каналов")
        return table

    def _make_message_handler(self, listener: ActiveFolderListener):
        async def handler(event: events.NewMessage.Event) -> None:
            channel_id = self._event_channel_id(event)

            links = self._extract_addlist_links(event.message)
            if not links:
                return

            source_title = getattr(event.chat, "title", "") or getattr(event.chat, "username", "") or str(channel_id)
            if not channel_id or channel_id not in listener.active_channel_ids:
                self._log(listener, "warn", f"Папка найдена в неотслеживаемом канале {source_title}, пропущена")
                return

            for slug, link_url in links.items():
                self._log(listener, "info", f"Поймана папка в канале {source_title}", event_type="folder-found")
                await self._process_addlist_link(listener, slug, link_url, channel_id, source_title)

        return handler

    async def _process_addlist_link(
        self,
        listener: ActiveFolderListener,
        slug: str,
        link_url: str,
        source_channel_id: int,
        source_title: str,
    ) -> None:
        async with listener.lock:
            if not self.db.start_folder_link_processing(
                slug,
                link_url,
                first_channel_id=source_channel_id,
                portal_user_id=listener.portal_user_id,
                portal_username=listener.portal_username,
            ):
                self._log(listener, "warn", "Повторная папка пропущена")
                return

            try:
                invite = await listener.client(CheckChatlistInviteRequest(slug))
                invite_channels = await self._resolve_invite_channels(listener.client, invite)
                self._log(listener, "info", f"Обнаружена папка ({len(invite_channels)} каналов) в канале {source_title}")
                self._log(listener, "scan", f"Сканирую {len(invite_channels)} каналов")

                new_entities = [entity for entity in invite_channels if int(getattr(entity, "id", 0) or 0) not in listener.active_channel_ids]
                input_peers = []
                for entity in new_entities:
                    entity_id = int(getattr(entity, "id", 0) or 0)
                    title = str(getattr(entity, "title", "") or getattr(entity, "username", "") or entity_id)
                    try:
                        await listener.client(JoinChannelRequest(entity))
                    except UserAlreadyParticipantError:
                        pass
                    except Exception as err:
                        self._log(listener, "warn", f"Не удалось вступить в канал {title}: {err}")
                    try:
                        input_peers.append(await listener.client.get_input_entity(entity))
                    except Exception as err:
                        self._log(listener, "warn", f"Не удалось подготовить канал {title} для добавления в папку: {err}")
                joined_chatlist_ids: set[int] = set()
                added_to_folder_ids: set[int] = set()
                if input_peers:
                    before_filter_ids = await self._dialog_filter_ids(listener.client)
                    try:
                        await listener.client(JoinChatlistInviteRequest(slug, peers=input_peers))
                        after_filter_ids = await self._dialog_filter_ids(listener.client)
                        joined_chatlist_ids = after_filter_ids - before_filter_ids
                    except Exception as err:
                        self._log(listener, "warn", f"Не удалось импортировать addlist через Telegram: {err}")
                    added_to_folder_ids = await self._add_peers_to_folder(listener, input_peers)
                    if len(added_to_folder_ids) < len(input_peers):
                        self._log(listener, "warn", f"В слушаемую папку добавлено {len(added_to_folder_ids)} из {len(input_peers)} каналов")

                folder_sources = await self._folder_source_channels(listener, invite_channels)
                active_before_update = set(listener.active_channel_ids)
                added = 0
                for entity in invite_channels:
                    entity_id = int(getattr(entity, "id"))
                    profile = await self._read_channel_profile(listener.client, entity, listener)
                    is_active_or_added = entity_id in listener.active_channel_ids or entity_id in added_to_folder_ids
                    row_id = self.db.upsert_folder_channel(
                        channel_id=entity_id,
                        title=profile["title"],
                        username=profile["username"],
                        link=profile["link"],
                        avatar_path=profile["avatar_path"],
                        subscribers=profile["subscribers"],
                        avg_views_10=profile["avg_views_10"],
                        source_channels=[source for source in folder_sources if source["id"] != str(entity_id)],
                        account_id=listener.account_id if is_active_or_added else None,
                        folder_id=listener.folder_id if is_active_or_added else "",
                        portal_user_id=listener.portal_user_id,
                        portal_username=listener.portal_username,
                    )
                    if row_id and entity_id in added_to_folder_ids and entity_id not in active_before_update:
                        listener.active_channel_ids.add(entity_id)
                        added += 1

                if joined_chatlist_ids:
                    await self._cleanup_joined_chatlists(listener, joined_chatlist_ids, input_peers)

                processing_status = "done" if len(added_to_folder_ids) >= len(input_peers) else "partial"
                self.db.finish_folder_link_processing(
                    slug,
                    channels_count=len(invite_channels),
                    status=processing_status,
                    portal_user_id=listener.portal_user_id,
                    portal_username=listener.portal_username,
                )
                if processing_status == "done":
                    self._log(listener, "success", f"{added} каналов добавлено в таблицу", event_type="channels-added")
                else:
                    self._log(listener, "warn", f"Папка обработана частично: {added} каналов добавлено, повтор разрешен")
            except Exception as err:
                self.db.finish_folder_link_processing(
                    slug,
                    channels_count=0,
                    status="failed",
                    portal_user_id=listener.portal_user_id,
                    portal_username=listener.portal_username,
                )
                self._log(listener, "warn", f"Ошибка обработки папки: {err}", event_type="parser-error")

    async def _sync_folder_channels(
        self,
        listener: ActiveFolderListener,
        folder_filter: DialogFilter | DialogFilterChatlist,
        source_channel: dict | None,
    ) -> set[int]:
        active_ids: set[int] = set()
        include_peers = list(getattr(folder_filter, "include_peers", []) or [])
        pinned_peers = list(getattr(folder_filter, "pinned_peers", []) or [])
        exclude_peers = list(getattr(folder_filter, "exclude_peers", []) or [])
        excluded_ids = {
            self._peer_channel_id(peer)
            for peer in exclude_peers
            if self._peer_channel_id(peer)
        }
        seen_ids: set[int] = set()
        titles: list[str] = []
        for peer in [*include_peers, *pinned_peers]:
            peer_channel_id = self._peer_channel_id(peer)
            if peer_channel_id and (peer_channel_id in excluded_ids or peer_channel_id in seen_ids):
                continue
            try:
                entity = await listener.client.get_entity(peer)
                channel_id = int(getattr(entity, "id", 0) or 0)
            except Exception:
                continue
            if channel_id <= 0:
                continue
            if not getattr(entity, "broadcast", False) and not getattr(entity, "megagroup", False):
                continue
            seen_ids.add(channel_id)
            active_ids.add(channel_id)
            titles.append(str(getattr(entity, "title", "") or getattr(entity, "username", "") or channel_id))
            profile = await self._read_channel_profile(listener.client, entity, listener)
            self.db.upsert_folder_channel(
                channel_id=channel_id,
                title=profile["title"],
                username=profile["username"],
                link=profile["link"],
                avatar_path=profile["avatar_path"],
                subscribers=profile["subscribers"],
                avg_views_10=profile["avg_views_10"],
                source_channels=[source_channel] if source_channel else [],
                account_id=listener.account_id,
                folder_id=listener.folder_id,
                portal_user_id=listener.portal_user_id,
                portal_username=listener.portal_username,
            )
        removed = self.db.unlink_stale_folder_channels(
            listener.account_id,
            listener.folder_id,
            active_ids,
            portal_user_id=listener.portal_user_id,
            portal_username=listener.portal_username,
        )
        visible_titles = ", ".join(titles[:10]) or "-"
        self._log(
            listener,
            "system",
            f"Синхронизация папки: видно {len(active_ids)}, include {len(include_peers)}, pinned {len(pinned_peers)}, exclude {len(exclude_peers)}, устаревших отвязано {removed}. Каналы: {visible_titles}",
        )
        return active_ids

    async def _add_peers_to_folder(self, listener: ActiveFolderListener, input_peers: list[Any]) -> set[int]:
        if not input_peers:
            return set()
        folder_filter = await self._get_folder_filter(listener.client, int(listener.folder_id))
        include_peers = list(getattr(folder_filter, "include_peers", []) or [])
        exclude_peers = list(getattr(folder_filter, "exclude_peers", []) or [])
        existing_ids = {self._input_peer_channel_id(peer) for peer in include_peers}
        target_ids = {self._input_peer_channel_id(peer) for peer in input_peers if self._input_peer_channel_id(peer)}
        added_ids: set[int] = set()
        for peer in input_peers:
            channel_id = self._input_peer_channel_id(peer)
            if channel_id and channel_id not in existing_ids:
                include_peers.append(peer)
                existing_ids.add(channel_id)
                added_ids.add(channel_id)
        folder_filter.include_peers = include_peers
        if target_ids:
            folder_filter.exclude_peers = [peer for peer in exclude_peers if self._peer_channel_id(peer) not in target_ids]
        try:
            await listener.client(UpdateDialogFilterRequest(int(listener.folder_id), folder_filter))
        except Exception as err:
            self._log(listener, "warn", f"Не удалось обновить слушаемую папку: {err}")
            return set()

        try:
            refreshed_filter = await self._get_folder_filter(listener.client, int(listener.folder_id))
            verified_ids = self._folder_filter_channel_ids(refreshed_filter)
        except Exception as err:
            self._log(listener, "warn", f"Не удалось проверить обновление слушаемой папки: {err}")
            return set()
        return target_ids & verified_ids

    def _folder_filter_channel_ids(self, folder_filter: DialogFilter | DialogFilterChatlist) -> set[int]:
        include_peers = list(getattr(folder_filter, "include_peers", []) or [])
        pinned_peers = list(getattr(folder_filter, "pinned_peers", []) or [])
        exclude_peers = list(getattr(folder_filter, "exclude_peers", []) or [])
        excluded_ids = {
            self._peer_channel_id(peer)
            for peer in exclude_peers
            if self._peer_channel_id(peer)
        }
        ids = {
            self._peer_channel_id(peer)
            for peer in [*include_peers, *pinned_peers]
            if self._peer_channel_id(peer)
        }
        return ids - excluded_ids

    async def _dialog_filter_ids(self, client: TelegramClient) -> set[int]:
        result = await client(GetDialogFiltersRequest())
        return {
            int(getattr(folder_filter, "id", -1))
            for folder_filter in list(getattr(result, "filters", result) or [])
            if int(getattr(folder_filter, "id", -1)) >= 0
        }

    async def _cleanup_joined_chatlists(
        self,
        listener: ActiveFolderListener,
        chatlist_ids: set[int],
        input_peers: list[Any],
    ) -> None:
        removed = 0
        for chatlist_id in chatlist_ids:
            if int(chatlist_id) == int(listener.folder_id):
                continue
            try:
                await listener.client(UpdateDialogFilterRequest(int(chatlist_id), None))
                removed += 1
            except Exception:
                pass
        if removed:
            self._log(listener, "system", f"Временная папка addlist удалена с аккаунта ({removed})")

    async def _resolve_invite_channels(self, client: TelegramClient, invite: Any) -> list[Any]:
        chats = list(getattr(invite, "chats", []) or [])
        peers = list(getattr(invite, "peers", []) or [])
        peers.extend(list(getattr(invite, "missing_peers", []) or []))
        peers.extend(list(getattr(invite, "already_peers", []) or []))
        wanted_ids = {self._peer_channel_id(peer) for peer in peers if self._peer_channel_id(peer)}
        entities = []
        for chat in chats:
            channel_id = int(getattr(chat, "id", 0) or 0)
            if channel_id <= 0:
                continue
            if wanted_ids and channel_id not in wanted_ids:
                continue
            if not getattr(chat, "broadcast", False) and not getattr(chat, "megagroup", False):
                continue
            entities.append(chat)
        return entities

    async def _folder_source_channels(self, listener: ActiveFolderListener, channels: list[Any]) -> list[dict]:
        sources = []
        for entity in channels:
            channel_id = int(getattr(entity, "id", 0) or 0)
            if channel_id <= 0:
                continue
            avatar_path = await self._download_channel_avatar(listener.client, entity, channel_id, listener)
            sources.append(
                {
                    "id": str(channel_id),
                    "title": str(getattr(entity, "title", "") or getattr(entity, "username", "") or channel_id),
                    "avatar_url": f"/media/avatars/{avatar_path}" if avatar_path else "",
                }
            )
        return sources

    async def _read_channel_profile(self, client: TelegramClient, entity: Any, listener: ActiveFolderListener) -> dict:
        channel_id = int(getattr(entity, "id", 0) or 0)
        title = str(getattr(entity, "title", "") or f"channel_{channel_id}")
        username = str(getattr(entity, "username", "") or "")
        link = f"https://t.me/{username}" if username else ""
        subscribers = int(getattr(entity, "participants_count", 0) or 0)
        try:
            full = await client(GetFullChannelRequest(entity))
            subscribers = int(getattr(getattr(full, "full_chat", None), "participants_count", subscribers) or subscribers)
        except Exception:
            pass

        views: list[int] = []
        try:
            async for message in client.iter_messages(entity, limit=6):
                views.append(int(getattr(message, "views", 0) or 0))
        except Exception:
            pass
        if len(views) > 1:
            views = views[1:6]
        avg_views = round(sum(views) / len(views)) if views else 0
        avatar_path = await self._download_channel_avatar(client, entity, channel_id, listener)
        return {
            "title": title,
            "username": f"@{username}" if username else "",
            "link": link,
            "subscribers": subscribers,
            "avg_views_10": avg_views,
            "avatar_path": avatar_path,
        }

    async def _download_channel_avatar(self, client: TelegramClient, entity: Any, channel_id: int, listener: ActiveFolderListener) -> str:
        owner_segment = self._owner_storage_segment(listener.portal_user_id, listener.portal_username)
        avatar_dir = self.settings.avatars_dir / owner_segment / "channels"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        avatar_name = f"{channel_id}.jpg"
        avatar_path = avatar_dir / avatar_name
        try:
            await client.download_profile_photo(entity, file=str(avatar_path), download_big=False)
            if avatar_path.exists() and avatar_path.stat().st_size > 0:
                return f"{owner_segment}/channels/{avatar_name}"
        except Exception:
            return ""
        return ""

    async def _get_folder_filter(self, client: TelegramClient, folder_id: int) -> DialogFilter | DialogFilterChatlist:
        result = await client(GetDialogFiltersRequest())
        for folder_filter in list(getattr(result, "filters", result) or []):
            if int(getattr(folder_filter, "id", -1)) == int(folder_id):
                return folder_filter
        raise ValueError("Папка не найдена")

    def _extract_addlist_links(self, message: Any) -> dict[str, str]:
        text = getattr(message, "message", "") or ""
        urls: list[str] = []
        urls.extend(match.group(0) for match in ADDLIST_RE.finditer(text))
        for entity in list(getattr(message, "entities", []) or []):
            if isinstance(entity, MessageEntityTextUrl):
                urls.append(entity.url)
            elif isinstance(entity, MessageEntityUrl):
                urls.append(text[entity.offset : entity.offset + entity.length])
        markup = getattr(message, "reply_markup", None)
        for row in list(getattr(markup, "rows", []) or []):
            for button in list(getattr(row, "buttons", []) or []):
                url = getattr(button, "url", "")
                if url:
                    urls.append(url)

        out: dict[str, str] = {}
        for url in urls:
            match = ADDLIST_RE.search(url or "")
            if match:
                slug = match.group(1)
                out[slug] = f"https://t.me/addlist/{slug}"
        return out

    def _channel_payload(self, row: dict) -> dict:
        avatar_path = row.get("avatar_path") or ""
        return {
            "id": str(row["channel_id"]),
            "channel_id": int(row["channel_id"]),
            "title": row.get("title") or "",
            "username": row.get("username") or "",
            "url": row.get("link") or "",
            "avatar_url": f"/media/avatars/{avatar_path}" if avatar_path else "",
            "subscribers": int(row.get("subscribers") or 0),
            "avg_views": int(row.get("avg_views_10") or 0),
            "added_at": row.get("created_at") or "",
            "updated_at": row.get("updated_at") or "",
            "check_status": row.get("review_status") or "unchecked",
            "source_channels": row.get("source_channels") or [],
        }

    def _listener_payload(self, listener: ActiveFolderListener, status: str) -> dict:
        return {
            "status": status,
            "listener_id": listener.listener_id,
            "account_id": listener.account_id,
            "folder_id": listener.folder_id,
            "folder_title": listener.folder_title,
            "channels": len(listener.active_channel_ids),
        }

    def _log(self, listener: ActiveFolderListener, log_type: str, message: str, event_type: str = "") -> None:
        self.db.add_folder_log(
            log_type,
            message,
            listener_id=listener.listener_id,
            portal_user_id=listener.portal_user_id,
            portal_username=listener.portal_username,
            event_type=event_type,
        )

    def _event_channel_id(self, event: events.NewMessage.Event) -> int:
        peer_id = getattr(getattr(event, "message", None), "peer_id", None)
        return int(getattr(peer_id, "channel_id", 0) or 0)

    def _peer_channel_id(self, peer: Any) -> int:
        return int(getattr(peer, "channel_id", 0) or 0)

    def _input_peer_channel_id(self, peer: Any) -> int:
        return int(getattr(peer, "channel_id", 0) or 0)

    def _dialog_filter_title(self, folder_filter: Any) -> str:
        raw_title = getattr(folder_filter, "title", "")
        if isinstance(raw_title, str):
            return raw_title.strip()
        text = getattr(raw_title, "text", "")
        if isinstance(text, str):
            return text.strip()
        return str(raw_title or "").strip()

    def _listener_key(self, portal_user_id: str, portal_username: str, account_id: int, folder_id: str) -> str:
        owner = portal_user_id or f"username:{portal_username}" or "anonymous"
        return f"{owner}:{account_id}:{folder_id}"

    def _owner_storage_segment(self, portal_user_id: str = "", portal_username: str = "") -> str:
        raw = portal_user_id or portal_username or "anonymous"
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw).strip("._-")
        return safe or "anonymous"

    def _close_session_storage(self, client: TelegramClient) -> None:
        try:
            session_obj = getattr(client, "session", None)
            if session_obj is not None:
                session_obj.close()
        except Exception:
            pass

    def _ensure_api_configured(self) -> None:
        if self.settings.api_id <= 0 or not self.settings.api_hash:
            raise ValueError("Укажите API_ID и API_HASH в .env")
