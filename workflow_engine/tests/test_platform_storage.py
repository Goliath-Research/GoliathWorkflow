"""Tests for gateway platform storage request merging."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REST = Path(__file__).resolve().parents[1] / "rest"
if str(_REST) not in sys.path:
    sys.path.insert(0, str(_REST))

from platform_storage import apply_platform_sample_storage  # noqa: E402


def test_apply_platform_storage_fills_missing_fields() -> None:
    row = {
        "bucket": "epimethyl",
        "region": "us-east-1",
        "endpoint_url": "https://s3.us-east-1.myqnapcloud.io",
        "access_key_id": "AKIA",
        "secret_access_key": "secret",
        "base_prefix": "samples/",
        "provider_type": "s3",
    }
    out = apply_platform_sample_storage({"projectPath": "/work/project.json"}, row)
    assert out["fastqStorage"]["bucket"] == "epimethyl"
    assert out["fastqStorage"]["endpointUrl"] == "https://s3.us-east-1.myqnapcloud.io"
    assert out["h5Storage"]["bucket"] == "epimethyl"


def test_apply_platform_storage_preserves_explicit_fastq() -> None:
    row = {
        "bucket": "epimethyl",
        "endpoint_url": "https://s3.us-east-1.myqnapcloud.io",
        "access_key_id": "AKIA",
        "secret_access_key": "secret",
        "base_prefix": "samples/",
        "provider_type": "s3",
    }
    body = {
        "fastqStorage": {
            "type": "s3",
            "bucket": "other",
            "credentials": {"authMode": "instance_profile"},
        }
    }
    out = apply_platform_sample_storage(body, row)
    assert out["fastqStorage"]["bucket"] == "other"
    assert out["h5Storage"]["bucket"] == "epimethyl"


def test_apply_platform_storage_requires_row_or_fastq() -> None:
    with pytest.raises(ValueError, match="fastqStorage is required"):
        apply_platform_sample_storage({}, None)
