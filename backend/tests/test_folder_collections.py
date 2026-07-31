from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.db import Database


class FolderCollectionDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "collections.db")
        self.db.init()
        self.table_id = self.db.ensure_channel_table("", "tester")
        self.db.upsert_folder_channel(
            channel_id=101,
            title="ATH Invest",
            username="athinvest",
            link="https://t.me/athinvest",
            subscribers=12500,
            avg_views_10=4300,
            portal_username="tester",
            table_id=self.table_id,
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_collection_and_items_are_persisted_for_owner(self) -> None:
        collection = self.db.create_folder_collection(
            self.table_id,
            "Июль",
            portal_username="tester",
        )
        item = self.db.add_folder_collection_item(
            collection["id"],
            portal_username="tester",
        )
        self.assertIsNotNone(item)

        saved_item = self.db.update_folder_collection_item(
            collection["id"],
            item["id"],
            channel_id=101,
            channel_ref="https://t.me/athinvest",
            admin_contact="@ath_admin",
            role="sponsor",
            portal_username="tester",
        )

        self.assertEqual(saved_item["channel_id"], 101)
        self.assertEqual(saved_item["admin_contact"], "@ath_admin")
        self.assertEqual(saved_item["role"], "sponsor")
        self.assertEqual(
            self.db.get_folder_channel(101, self.table_id)["admin_contact"],
            "@ath_admin",
        )

        collections = self.db.list_folder_collections(
            self.table_id,
            portal_username="tester",
        )
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0]["title"], "Июль")
        self.assertEqual(collections[0]["items"], [saved_item])

    def test_channel_admin_is_shared_by_all_collection_rows(self) -> None:
        collections = [
            self.db.create_folder_collection(
                self.table_id,
                title,
                portal_username="tester",
            )
            for title in ("Первая", "Вторая")
        ]
        items = [
            self.db.add_folder_collection_item(
                collection["id"],
                portal_username="tester",
            )
            for collection in collections
        ]
        for collection, item in zip(collections, items):
            self.db.update_folder_collection_item(
                collection["id"],
                item["id"],
                channel_id=101,
                channel_ref="https://t.me/athinvest",
                admin_contact="",
                role="member",
                portal_username="tester",
            )

        self.assertTrue(self.db.set_folder_channel_admin(101, self.table_id, "@global_admin"))

        stored = self.db.list_folder_collections(self.table_id, portal_username="tester")
        self.assertEqual(
            [collection["items"][0]["admin_contact"] for collection in stored],
            ["@global_admin", "@global_admin"],
        )

    def test_collection_is_isolated_by_portal_owner(self) -> None:
        collection = self.db.create_folder_collection(
            self.table_id,
            "Приватная",
            portal_username="tester",
        )

        self.assertEqual(
            self.db.list_folder_collections(self.table_id, portal_username="other"),
            [],
        )
        self.assertIsNone(
            self.db.add_folder_collection_item(collection["id"], portal_username="other")
        )
        self.assertFalse(
            self.db.delete_folder_collection(collection["id"], portal_username="other")
        )

    def test_deleting_collection_removes_its_items(self) -> None:
        collection = self.db.create_folder_collection(
            self.table_id,
            "На удаление",
            portal_username="tester",
        )
        item = self.db.add_folder_collection_item(
            collection["id"],
            portal_username="tester",
        )

        self.assertTrue(
            self.db.delete_folder_collection(collection["id"], portal_username="tester")
        )
        stored_item = self.db.conn.execute(
            "SELECT id FROM folder_collection_items WHERE id = ?",
            (item["id"],),
        ).fetchone()
        self.assertIsNone(stored_item)

    def test_item_role_is_limited_to_member_or_sponsor(self) -> None:
        collection = self.db.create_folder_collection(
            self.table_id,
            "Роли",
            portal_username="tester",
        )
        item = self.db.add_folder_collection_item(
            collection["id"],
            portal_username="tester",
        )

        with self.assertRaisesRegex(ValueError, "Неизвестная роль"):
            self.db.update_folder_collection_item(
                collection["id"],
                item["id"],
                channel_id=None,
                channel_ref="@unknown",
                admin_contact="",
                role="bad",
                portal_username="tester",
            )

    def test_username_owned_collection_follows_table_merge(self) -> None:
        collection = self.db.create_folder_collection(
            self.table_id,
            "До Portal ID",
            portal_username="tester",
        )
        current_table_id = self.db.ensure_channel_table("portal-42", "tester")

        self.db.bind_portal_username_to_user_id("portal-42", "tester")

        migrated = self.db.get_folder_collection(
            collection["id"],
            portal_user_id="portal-42",
            portal_username="tester",
        )
        self.assertIsNotNone(migrated)
        self.assertEqual(migrated["table_id"], current_table_id)


if __name__ == "__main__":
    unittest.main()
