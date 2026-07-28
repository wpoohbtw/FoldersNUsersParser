from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.app.db import Database
from backend.app.folder_parser_service import ActiveFolderListener, FolderParserService
from backend.app.telegram_bot_service import TelegramBotService


class FakeTelegramClient:
    def __init__(self) -> None:
        self.references: list[object] = []
        self.requests: list[object] = []

    async def get_input_entity(self, reference: object) -> object:
        self.references.append(reference)
        return reference

    async def __call__(self, request: object) -> None:
        self.requests.append(request)


class ChannelReviewDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "review.db"
        self.db = Database(self.db_path)
        self.db.init()
        self.table_id = self.db.ensure_channel_table("", "tester")

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def add_channel(self, channel_id: int, title: str) -> None:
        self.db.upsert_folder_channel(
            channel_id=channel_id,
            title=title,
            username=title.lower(),
            account_id=10,
            folder_id="20",
            portal_username="tester",
            table_id=self.table_id,
        )

    def test_queue_is_oldest_first_and_saved_labels_remove_channel(self) -> None:
        self.add_channel(101, "First")
        self.add_channel(202, "Second")

        queue = self.db.list_unchecked_channels_for_table(self.table_id, "", "tester")
        self.assertEqual([row["channel_id"] for row in queue], [101, 202])

        self.db.save_folder_channel_labels(
            101,
            self.table_id,
            is_member=True,
            is_sponsor=True,
            is_bad=False,
        )

        saved = self.db.get_folder_channel(101, self.table_id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["review_status"], "checked")
        self.assertTrue(saved["is_member"])
        self.assertTrue(saved["is_sponsor"])
        self.assertFalse(self.db.is_channel_blacklisted(101, self.table_id))
        payload = FolderParserService(SimpleNamespace(), self.db)._channel_payload(saved)
        self.assertTrue(payload["is_member"])
        self.assertTrue(payload["is_sponsor"])
        queue = self.db.list_unchecked_channels_for_table(self.table_id, "", "tester")
        self.assertEqual([row["channel_id"] for row in queue], [202])

    def test_bad_label_blacklists_channel_until_reset(self) -> None:
        self.add_channel(303, "Bad")

        self.db.save_folder_channel_labels(
            303,
            self.table_id,
            is_member=False,
            is_sponsor=False,
            is_bad=True,
        )

        self.assertTrue(self.db.is_channel_blacklisted(303, self.table_id))
        self.assertIsNone(
            self.db.upsert_folder_channel(
                channel_id=303,
                title="Bad again",
                portal_username="tester",
                table_id=self.table_id,
            )
        )

        self.db.set_folder_channel_review_status(303, "unchecked", self.table_id)
        restored = self.db.get_folder_channel(303, self.table_id)
        self.assertFalse(self.db.is_channel_blacklisted(303, self.table_id))
        self.assertFalse(restored["is_member"])
        self.assertFalse(restored["is_sponsor"])

    def test_legacy_rejected_status_does_not_create_blacklist_entry(self) -> None:
        self.add_channel(404, "Legacy")

        self.db.set_folder_channel_review_status(404, "rejected", self.table_id)

        self.assertFalse(self.db.is_channel_blacklisted(404, self.table_id))

    def test_existing_database_gets_label_columns_and_blacklist_table(self) -> None:
        self.db.conn.execute("DROP TABLE channel_blacklist")
        self.db.conn.execute("ALTER TABLE folder_channels DROP COLUMN is_member")
        self.db.conn.execute("ALTER TABLE folder_channels DROP COLUMN is_sponsor")
        self.db.conn.commit()
        self.db.close()

        self.db = Database(self.db_path)
        self.db.init()

        columns = {
            row["name"]
            for row in self.db.conn.execute("PRAGMA table_info(folder_channels)").fetchall()
        }
        blacklist_table = self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'channel_blacklist'"
        ).fetchone()
        self.assertIn("is_member", columns)
        self.assertIn("is_sponsor", columns)
        self.assertIsNotNone(blacklist_table)

    def test_bot_keyboard_marks_selected_labels(self) -> None:
        self.add_channel(606, "Keyboard")
        service = TelegramBotService(self.db)

        service._toggle_review_label("", "tester", 606, "member")
        service._toggle_review_label("", "tester", 606, "sponsor")
        _text, keyboard = service._review_payload("", "tester", self.table_id, 0)
        self.assertEqual(
            [button.text for button in keyboard.inline_keyboard[0]],
            ["✅ Участник", "✅ $", "Хуйня"],
        )

        service._toggle_review_label("", "tester", 606, "bad")
        _text, keyboard = service._review_payload("", "tester", self.table_id, 0)
        self.assertEqual(
            [button.text for button in keyboard.inline_keyboard[0]],
            ["Участник", "$", "✅ Хуйня"],
        )


class TelegramBotSelectionTests(unittest.TestCase):
    def test_positive_labels_combine_and_bad_label_is_exclusive(self) -> None:
        service = TelegramBotService(SimpleNamespace())

        self.assertEqual(service._toggle_review_label("", "tester", 1, "member"), {"member"})
        self.assertEqual(service._toggle_review_label("", "tester", 1, "sponsor"), {"member", "sponsor"})
        self.assertEqual(service._toggle_review_label("", "tester", 1, "bad"), {"bad"})
        self.assertEqual(service._toggle_review_label("", "tester", 1, "member"), {"member"})
        self.assertEqual(service._toggle_review_label("", "tester", 1, "sponsor"), {"member", "sponsor"})


class FolderBlacklistRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "runtime.db")
        self.db.init()
        self.table_id = self.db.ensure_channel_table("", "tester")
        self.db.upsert_folder_channel(
            channel_id=505,
            title="Blocked",
            username="blocked",
            account_id=10,
            folder_id="20",
            portal_username="tester",
            table_id=self.table_id,
        )
        self.db.save_folder_channel_labels(
            505,
            self.table_id,
            is_member=False,
            is_sponsor=False,
            is_bad=True,
        )

    async def asyncTearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    async def test_active_listener_stops_tracking_and_leaves_blacklisted_channel(self) -> None:
        client = FakeTelegramClient()
        placeholder_task = asyncio.create_task(asyncio.sleep(0))
        listener = ActiveFolderListener(
            key="username:tester:10:20",
            listener_id=1,
            portal_user_id="",
            portal_username="tester",
            account_id=10,
            folder_id="20",
            folder_title="Watcher",
            client=client,
            task=placeholder_task,
            active_channel_ids={505},
        )
        service = FolderParserService(SimpleNamespace(), self.db)
        service._listeners[listener.key] = listener

        affected = await service.blacklist_channel(self.table_id, 505)
        await asyncio.gather(*list(service._background_tasks))

        self.assertTrue(affected)
        self.assertNotIn(505, listener.active_channel_ids)
        self.assertEqual(client.references, ["blocked"])
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(service._stored_listener_channel_ids(listener), set())
        await placeholder_task
