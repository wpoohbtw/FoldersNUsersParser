from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html import escape
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .db import Database


@dataclass(slots=True)
class RunningTelegramBot:
    key: str
    portal_user_id: str
    portal_username: str
    allowed_username: str
    bot: Bot
    dispatcher: Dispatcher
    task: asyncio.Task


class TelegramBotService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._bots: dict[str, RunningTelegramBot] = {}
        self._lock = asyncio.Lock()

    async def restore_running_bots(self) -> None:
        for config in self.db.list_running_telegram_bot_configs():
            try:
                await self.start_bot(config)
            except Exception:
                self.db.set_telegram_bot_running(
                    False,
                    portal_user_id=config.get("portal_user_id") or "",
                    portal_username=config.get("portal_username") or "",
                )

    def get_config(self, portal_user_id: str = "", portal_username: str = "") -> dict:
        config = self.db.get_telegram_bot_config(portal_user_id, portal_username)
        config["is_running"] = self._runtime_key(portal_user_id, portal_username) in self._bots
        return config

    async def save_config(self, bot_token: str, allowed_username: str, portal_user_id: str = "", portal_username: str = "") -> dict:
        current = self.db.get_telegram_bot_config(portal_user_id, portal_username)
        if current.get("is_running") and str(current.get("bot_token") or "") != bot_token.strip():
            await self.stop_bot(portal_user_id, portal_username, mark_stopped=True)
        return self.db.upsert_telegram_bot_config(bot_token, allowed_username, portal_user_id, portal_username)

    async def start_bot(self, config: dict) -> dict:
        portal_user_id = config.get("portal_user_id") or ""
        portal_username = config.get("portal_username") or ""
        bot_token = str(config.get("bot_token") or "").strip()
        allowed_username = str(config.get("allowed_username") or "").strip().lstrip("@")
        if not bot_token:
            raise ValueError("Укажите API бота")
        if not allowed_username:
            raise ValueError("Укажите username пользователя")

        key = self._runtime_key(portal_user_id, portal_username)
        async with self._lock:
            if key in self._bots:
                self.db.set_telegram_bot_running(True, portal_user_id, portal_username)
                return self.get_config(portal_user_id, portal_username)

            bot = Bot(bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            try:
                await bot.get_me()
            except Exception:
                await bot.session.close()
                raise
            dispatcher = Dispatcher()
            router = self._build_router(portal_user_id, portal_username, allowed_username)
            dispatcher.include_router(router)
            task = asyncio.create_task(dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"]))
            self._bots[key] = RunningTelegramBot(
                key=key,
                portal_user_id=portal_user_id,
                portal_username=portal_username,
                allowed_username=allowed_username.lower(),
                bot=bot,
                dispatcher=dispatcher,
                task=task,
            )
            task.add_done_callback(lambda _task: self._bots.pop(key, None))
            self.db.set_telegram_bot_running(True, portal_user_id, portal_username)
        return self.get_config(portal_user_id, portal_username)

    async def stop_bot(self, portal_user_id: str = "", portal_username: str = "", mark_stopped: bool = True) -> dict:
        key = self._runtime_key(portal_user_id, portal_username)
        async with self._lock:
            runtime = self._bots.pop(key, None)
        if runtime:
            runtime.task.cancel()
            try:
                await runtime.dispatcher.stop_polling()
            except Exception:
                pass
            try:
                await runtime.bot.session.close()
            except Exception:
                pass
        if mark_stopped:
            self.db.set_telegram_bot_running(False, portal_user_id, portal_username)
        return self.get_config(portal_user_id, portal_username)

    async def stop_all(self) -> None:
        runtimes = list(self._bots.values())
        self._bots.clear()
        for runtime in runtimes:
            runtime.task.cancel()
            try:
                await runtime.dispatcher.stop_polling()
            except Exception:
                pass
            try:
                await runtime.bot.session.close()
            except Exception:
                pass

    async def notify_folder_added(
        self,
        portal_user_id: str,
        portal_username: str,
        source_title: str,
        source_url: str,
        channels_added: int,
    ) -> None:
        runtime = self._bots.get(self._runtime_key(portal_user_id, portal_username))
        config = self.db.get_telegram_bot_config(portal_user_id, portal_username)
        chat_id = config.get("chat_id")
        if not runtime or not chat_id:
            return
        source = self._html_link(source_title, source_url)
        text = f"Папка поймана в канале {source}.\nКаналов добавлено: <b>{int(channels_added)}</b>."
        try:
            await runtime.bot.send_message(int(chat_id), text, disable_web_page_preview=True)
        except Exception:
            pass

    def _build_router(self, portal_user_id: str, portal_username: str, allowed_username: str) -> Router:
        router = Router()

        @router.message(CommandStart())
        async def handle_start(message: Message) -> None:
            if not self._is_allowed(message.from_user, allowed_username):
                denied = await message.answer("Нет доступа.")
                self._forget_later(message.bot, denied.chat.id, denied.message_id)
                return
            text, keyboard = self._main_menu_payload(portal_user_id, portal_username)
            sent = await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
            self.db.update_telegram_bot_main_message(
                sent.chat.id,
                sent.message_id,
                portal_user_id=portal_user_id,
                portal_username=portal_username,
            )

        @router.callback_query(F.data == "refresh")
        async def handle_refresh(callback: CallbackQuery) -> None:
            if not await self._accept_callback(callback, portal_user_id, portal_username, allowed_username):
                return
            await self._edit_main(callback, *self._main_menu_payload(portal_user_id, portal_username))

        @router.callback_query(F.data == "menu")
        async def handle_menu(callback: CallbackQuery) -> None:
            if not await self._accept_callback(callback, portal_user_id, portal_username, allowed_username):
                return
            self.db.update_telegram_bot_ui_state(None, 0, portal_user_id, portal_username)
            await self._edit_main(callback, *self._main_menu_payload(portal_user_id, portal_username))

        @router.callback_query(F.data.startswith("table:"))
        async def handle_table(callback: CallbackQuery) -> None:
            if not await self._accept_callback(callback, portal_user_id, portal_username, allowed_username):
                return
            table_id = self._callback_int(callback.data, "table:")
            self.db.update_telegram_bot_ui_state(table_id, 0, portal_user_id, portal_username)
            await self._edit_main(callback, *self._review_payload(portal_user_id, portal_username, table_id, 0))

        @router.callback_query(F.data.in_({"approve", "reject", "prev", "next"}))
        async def handle_review(callback: CallbackQuery) -> None:
            if not await self._accept_callback(callback, portal_user_id, portal_username, allowed_username):
                return
            config = self.db.get_telegram_bot_config(portal_user_id, portal_username)
            table_id = config.get("selected_table_id")
            if not table_id:
                await self._edit_main(callback, *self._main_menu_payload(portal_user_id, portal_username))
                return

            channels = self.db.list_unchecked_channels_for_table(int(table_id), portal_user_id, portal_username)
            if not channels:
                await self._edit_main(callback, *self._main_menu_payload(portal_user_id, portal_username))
                return

            index = min(max(0, int(config.get("selected_index") or 0)), len(channels) - 1)
            action = str(callback.data or "")
            if action in {"approve", "reject"}:
                status = "checked" if action == "approve" else "rejected"
                self.db.set_folder_channel_review_status(int(channels[index]["channel_id"]), status, int(table_id))
                channels = self.db.list_unchecked_channels_for_table(int(table_id), portal_user_id, portal_username)
                index = min(index, max(0, len(channels) - 1))
            elif action == "prev":
                index = max(0, index - 1)
            elif action == "next":
                index = min(len(channels) - 1, index + 1)

            self.db.update_telegram_bot_ui_state(int(table_id), index, portal_user_id, portal_username)
            await self._edit_main(callback, *self._review_payload(portal_user_id, portal_username, int(table_id), index))

        return router

    def _main_menu_payload(self, portal_user_id: str, portal_username: str) -> tuple[str, InlineKeyboardMarkup]:
        tables = self.db.list_channel_tables_with_unchecked_counts(portal_user_id, portal_username)
        rows: list[list[InlineKeyboardButton]] = []
        if not tables:
            text = "Нет каналов на проверку."
        else:
            text = "Выберите таблицу каналов для проверки."
            for table in tables:
                title = str(table.get("title") or f"Таблица {table['id']}")
                rows.append([InlineKeyboardButton(text=f"📋 {title} ({table['unchecked_count']})", callback_data=f"table:{table['id']}")])
        rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")])
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    def _review_payload(self, portal_user_id: str, portal_username: str, table_id: int, index: int) -> tuple[str, InlineKeyboardMarkup]:
        channels = self.db.list_unchecked_channels_for_table(table_id, portal_user_id, portal_username)
        if not channels:
            return self._main_menu_payload(portal_user_id, portal_username)

        index = min(max(0, int(index)), len(channels) - 1)
        channel = channels[index]
        title = self._html_link(str(channel.get("title") or "Канал"), str(channel.get("link") or ""))
        subscribers = int(channel.get("subscribers") or 0)
        avg_views = int(channel.get("avg_views_10") or 0)
        text = f"{title} | пдп: <b>{subscribers}</b> | avg.views: <b>{avg_views}</b>"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подходит", callback_data="approve"),
                    InlineKeyboardButton(text="❌ Не подходит", callback_data="reject"),
                ],
                [
                    InlineKeyboardButton(text="⬅️", callback_data="prev"),
                    InlineKeyboardButton(text=f"{index + 1}/{len(channels)}", callback_data="refresh"),
                    InlineKeyboardButton(text="➡️", callback_data="next"),
                ],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]
        )
        return text, keyboard

    async def _accept_callback(
        self,
        callback: CallbackQuery,
        portal_user_id: str,
        portal_username: str,
        allowed_username: str,
    ) -> bool:
        if not self._is_allowed(callback.from_user, allowed_username):
            await callback.answer("Нет доступа", show_alert=False)
            return False
        config = self.db.get_telegram_bot_config(portal_user_id, portal_username)
        message = callback.message
        if not message or int(getattr(message, "message_id", 0) or 0) != int(config.get("main_message_id") or 0):
            await callback.answer("Нажмите /start, чтобы открыть актуальное меню", show_alert=False)
            return False
        await callback.answer()
        return True

    async def _edit_main(self, callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup) -> None:
        if not callback.message:
            return
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
        except TelegramBadRequest as err:
            if "message is not modified" not in str(err).lower():
                raise

    def _is_allowed(self, user: Any, allowed_username: str) -> bool:
        username = str(getattr(user, "username", "") or "").strip().lstrip("@")
        return bool(username and username.lower() == allowed_username.strip().lstrip("@").lower())

    def _callback_int(self, value: str | None, prefix: str) -> int:
        raw = str(value or "")
        if not raw.startswith(prefix):
            return 0
        try:
            return int(raw[len(prefix) :])
        except ValueError:
            return 0

    def _html_link(self, title: str, url: str) -> str:
        safe_title = escape(title or "Канал")
        safe_url = escape(url or "", quote=True)
        if not safe_url:
            return safe_title
        return f'<a href="{safe_url}">{safe_title}</a>'

    def _runtime_key(self, portal_user_id: str = "", portal_username: str = "") -> str:
        return portal_user_id or f"username:{portal_username}" or "anonymous"

    def _forget_later(self, bot: Bot, chat_id: int, message_id: int) -> None:
        async def cleanup() -> None:
            await asyncio.sleep(8)
            try:
                await bot.delete_message(chat_id, message_id)
            except Exception:
                pass

        asyncio.create_task(cleanup())
