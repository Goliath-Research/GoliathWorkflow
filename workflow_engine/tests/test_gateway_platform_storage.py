"""Tests for portal archive profile resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PORTAL = Path(__file__).resolve().parents[1] / "portal"
if str(_PORTAL) not in sys.path:
    sys.path.insert(0, str(_PORTAL))

from archive_profile_resolver import apply_archive_profile_storage  # noqa: E402
from resource_profile import ResourceProfileReader  # noqa: E402

_LAB_FASTQ = {
    "type": "s3",
    "bucket": "lab-cohort",
    "region": "us-west-2",
    "credentials": {"authMode": "instance_profile"},
}

_PROFILE_JSON = {
    "type": "s3",
    "bucket": "epimethyl",
    "region": "us-east-1",
    "endpointUrl": "https://s3.us-east-1.myqnapcloud.io",
    "prefixBase": "samples/",
    "credentials": {
        "authMode": "explicit_keys",
        "accessKeyId": "AKIA",
        "secretAccessKey": "secret",
    },
}


def test_apply_archive_profile_fills_h5_only() -> None:
    def loader(_key: str) -> dict:
        return dict(_PROFILE_JSON)

    out = apply_archive_profile_storage(
        {"projectPath": "/work/project.json", "fastqStorage": _LAB_FASTQ},
        loader,
    )
    assert out["fastqStorage"]["bucket"] == "lab-cohort"
    assert out["h5Storage"]["bucket"] == "epimethyl"


def test_apply_archive_profile_preserves_explicit_h5() -> None:
    body = {
        "fastqStorage": _LAB_FASTQ,
        "h5Storage": {
            "type": "s3",
            "bucket": "custom-archive",
            "credentials": {"authMode": "instance_profile"},
        },
    }
    out = apply_archive_profile_storage(body, lambda _k: dict(_PROFILE_JSON))
    assert out["h5Storage"]["bucket"] == "custom-archive"


def test_apply_archive_profile_requires_lab_fastq() -> None:
    with pytest.raises(ValueError, match="laboratory-owned"):
        apply_archive_profile_storage({}, lambda _k: dict(_PROFILE_JSON))


def test_resource_profile_reader_parses_json() -> None:
    db = MagicMock()
    db.backend = "postgres"
    db._fetch_one.return_value = {
        "profile_key": "epimethyl-samples",
        "profile_type": "s3_object_storage",
        "profile_json": _PROFILE_JSON,
        "status": "ACTIVE",
    }
    reader = ResourceProfileReader(db)
    h5 = reader.h5_storage_defaults("epimethyl-samples")
    assert h5 is not None
    assert h5["bucket"] == "epimethyl"
    assert h5["endpointUrl"] == "https://s3.us-east-1.myqnapcloud.io"
    assert h5["credentials"]["secretAccessKey"] == "secret"
