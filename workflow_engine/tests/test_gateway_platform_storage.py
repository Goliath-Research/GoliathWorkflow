"""Tests for gateway platform archive storage request merging."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REST = Path(__file__).resolve().parents[1] / "rest"
if str(_REST) not in sys.path:
    sys.path.insert(0, str(_REST))

from platform_storage import apply_platform_archive_storage  # noqa: E402

_LAB_FASTQ = {
    "type": "s3",
    "bucket": "lab-cohort",
    "region": "us-west-2",
    "credentials": {"authMode": "instance_profile"},
}


def test_apply_archive_storage_fills_h5_only() -> None:
    row = {
        "bucket": "epimethyl",
        "region": "us-east-1",
        "endpoint_url": "https://s3.us-east-1.myqnapcloud.io",
        "access_key_id": "AKIA",
        "secret_access_key": "secret",
        "base_prefix": "samples/",
        "provider_type": "s3",
    }
    out = apply_platform_archive_storage(
        {"projectPath": "/work/project.json", "fastqStorage": _LAB_FASTQ},
        row,
    )
    assert out["fastqStorage"]["bucket"] == "lab-cohort"
    assert out["h5Storage"]["bucket"] == "epimethyl"
    assert out["h5Storage"]["endpointUrl"] == "https://s3.us-east-1.myqnapcloud.io"


def test_apply_archive_storage_preserves_explicit_h5() -> None:
    row = {
        "bucket": "epimethyl",
        "endpoint_url": "https://s3.us-east-1.myqnapcloud.io",
        "access_key_id": "AKIA",
        "secret_access_key": "secret",
        "base_prefix": "samples/",
        "provider_type": "s3",
    }
    body = {
        "fastqStorage": _LAB_FASTQ,
        "h5Storage": {
            "type": "s3",
            "bucket": "custom-archive",
            "credentials": {"authMode": "instance_profile"},
        },
    }
    out = apply_platform_archive_storage(body, row)
    assert out["h5Storage"]["bucket"] == "custom-archive"


def test_apply_archive_storage_requires_lab_fastq_even_with_platform_row() -> None:
    row = {
        "bucket": "epimethyl",
        "endpoint_url": "https://s3.us-east-1.myqnapcloud.io",
        "access_key_id": "AKIA",
        "secret_access_key": "secret",
        "base_prefix": "samples/",
        "provider_type": "s3",
    }
    with pytest.raises(ValueError, match="laboratory-owned"):
        apply_platform_archive_storage({}, row)
