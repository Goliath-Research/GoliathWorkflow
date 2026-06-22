"""Tests for Azure managed identity token provider."""

from __future__ import annotations

import sys
import struct
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REST_DIR))

from rest.azure_auth import (  # noqa: E402
    _MSSQL_RESOURCE,
    _POSTGRES_RESOURCE,
    clear_token_cache,
    get_database_access_token,
    mssql_access_token_bytes,
)
from rest.connection import DatabaseBackend  # noqa: E402


class _FakeToken:
    def __init__(self, token: str, expires_on: float) -> None:
        self.token = token
        self.expires_on = expires_on


class AzureAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_token_cache()

    def tearDown(self) -> None:
        clear_token_cache()

    @patch("azure.identity.DefaultAzureCredential")
    def test_mssql_token_fetched_and_cached(self, mock_cred_cls: MagicMock) -> None:
        mock_cred = MagicMock()
        mock_cred_cls.return_value = mock_cred
        mock_cred.get_token.return_value = _FakeToken("tok-mssql", time.time() + 3600)

        first = get_database_access_token(DatabaseBackend.MSSQL)
        second = get_database_access_token(DatabaseBackend.MSSQL)

        self.assertEqual(first, "tok-mssql")
        self.assertEqual(second, "tok-mssql")
        mock_cred.get_token.assert_called_once_with(_MSSQL_RESOURCE)

    @patch("azure.identity.DefaultAzureCredential")
    def test_postgres_uses_distinct_resource(self, mock_cred_cls: MagicMock) -> None:
        mock_cred = MagicMock()
        mock_cred_cls.return_value = mock_cred
        mock_cred.get_token.return_value = _FakeToken("tok-pg", time.time() + 3600)

        token = get_database_access_token(DatabaseBackend.POSTGRES)

        self.assertEqual(token, "tok-pg")
        mock_cred.get_token.assert_called_once_with(_POSTGRES_RESOURCE)

    @patch("azure.identity.DefaultAzureCredential")
    def test_token_refreshes_near_expiry(self, mock_cred_cls: MagicMock) -> None:
        mock_cred = MagicMock()
        mock_cred_cls.return_value = mock_cred
        mock_cred.get_token.side_effect = [
            _FakeToken("old", time.time() + 100),
            _FakeToken("new", time.time() + 3600),
        ]

        self.assertEqual(get_database_access_token(DatabaseBackend.MSSQL), "old")
        self.assertEqual(get_database_access_token(DatabaseBackend.MSSQL), "new")
        self.assertEqual(mock_cred.get_token.call_count, 2)

    @patch("rest.azure_auth.get_database_access_token")
    def test_mssql_token_utf16_le_with_length_prefix(self, mock_get: MagicMock) -> None:
        mock_get.return_value = "abc"
        encoded = "abc".encode("utf-16-le")
        expected = struct.pack("<I", len(encoded)) + encoded
        self.assertEqual(mssql_access_token_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
