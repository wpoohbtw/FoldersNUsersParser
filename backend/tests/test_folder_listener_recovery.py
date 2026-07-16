from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.folder_parser_service import FolderParserService


class FakeDatabase:
    def __init__(self) -> None:
        self.listener = {
            "id": 7,
            "account_id": 11,
            "folder_id": "42",
            "status": "restoring",
            "portal_user_id": "1",
            "portal_username": "tester",
        }
        self.status_updates: list[str] = []
        self.logs: list[tuple[str, str]] = []

    def get_folder_listener(self, *_args, **_kwargs):
        return dict(self.listener)

    def set_folder_listener_status(self, _account_id, _folder_id, status, **_kwargs) -> None:
        self.listener["status"] = status
        self.status_updates.append(status)

    def add_folder_log(self, log_type, message, **_kwargs) -> None:
        self.logs.append((log_type, message))


class RecoveringFolderParser(FolderParserService):
    def __init__(self, database: FakeDatabase, outcomes: list[object]) -> None:
        super().__init__(SimpleNamespace(), database)
        self.outcomes = iter(outcomes)
        self.start_calls = 0

    async def start_listener(self, account, folder_id, portal_user_id="", portal_username=""):
        self.start_calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        self.db.set_folder_listener_status(account["id"], folder_id, "running", portal_user_id=portal_user_id, portal_username=portal_username)
        return outcome


class FolderListenerRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_failure_retries_until_listener_starts(self) -> None:
        database = FakeDatabase()
        service = RecoveringFolderParser(database, [TimeoutError("Telegram unavailable"), {"status": "running"}])
        delays: list[int] = []

        async def record_sleep(delay: int) -> None:
            delays.append(delay)

        with patch("backend.app.folder_parser_service.asyncio.sleep", new=record_sleep):
            await service._restore_listener_with_retry({"id": 11}, dict(database.listener))

        self.assertEqual(service.start_calls, 2)
        self.assertEqual(delays, [10])
        self.assertEqual(database.listener["status"], "running")
        self.assertEqual([log_type for log_type, _message in database.logs], ["warn", "system"])

    async def test_invalid_session_stops_recovery_without_retry(self) -> None:
        database = FakeDatabase()
        service = RecoveringFolderParser(database, [ValueError("Session is not authorized")])

        await service._restore_listener_with_retry({"id": 11}, dict(database.listener))

        self.assertEqual(service.start_calls, 1)
        self.assertEqual(database.listener["status"], "idle")
        self.assertEqual(len(database.logs), 1)
        self.assertEqual(database.logs[0][0], "warn")

