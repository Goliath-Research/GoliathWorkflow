"""Tests for admin HTTP client error handling."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import urllib.error

WF_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WF_ENGINE))

from rest.admin_client import admin_request  # noqa: E402


def test_admin_request_includes_http_error_body() -> None:
    err = urllib.error.HTTPError(
        url="http://localhost:8080/v1/admin/catalog/seed",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(b'{"error":"missing admin role"}'),
    )

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="HTTP 401: .*missing admin role"):
            admin_request("POST", "/admin/catalog/seed", {"catalog": {"actions": []}})
