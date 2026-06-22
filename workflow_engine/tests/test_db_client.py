"""Tests for db_client ephemeral DSN lifecycle."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REST_DIR))

from rest.db_client import worker_authenticate  # noqa: E402


class DbClientDsnLifecycleTests(unittest.TestCase):
    def test_dsn_string_closes_ephemeral_db(self) -> None:
        fake_db = mock.Mock()

        with mock.patch("rest.db_client.open_db_from_dsn", return_value=fake_db) as open_db:
            worker_authenticate("postgresql://u:p@host/db", 1, "tok")

        open_db.assert_called_once_with("postgresql://u:p@host/db")
        fake_db.worker_authenticate.assert_called_once_with(1, "tok")
        fake_db.close.assert_called_once()

    def test_gateway_db_instance_not_closed(self) -> None:
        fake_db = mock.Mock()

        worker_authenticate(fake_db, 2, "tok2")

        fake_db.worker_authenticate.assert_called_once_with(2, "tok2")
        fake_db.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
