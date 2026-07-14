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


def test_resource_profile_reader_expands_cfg_endpoint_ref() -> None:
    db = MagicMock()
    db.backend = "postgres"

    def fetch(sql: str, params: tuple = ()):
        if "portal.resource_profile" in sql:
            return {
                "profile_key": "epimethyl-samples",
                "profile_type": "cfg_storage_endpoint_ref",
                "profile_json": {
                    "sampleStorageEndpoint": "epimethyl-archive",
                    "prefixBase": "samples/",
                    "scope": "archive",
                },
                "status": "ACTIVE",
            }
        if "cfg.storage_endpoint" in sql:
            return {
                "location_json": {
                    "type": "s3",
                    "bucket": "epimethyl",
                    "region": "us-east-1",
                    "endpointUrl": "https://s3.us-east-1.myqnapcloud.io",
                    "scope": "archive",
                },
                "provider": "s3",
                "credential_name": "epimethyl-archive-keys",
                "endpoint_version": "1",
                "secret_json": {
                    "authMode": "explicit_keys",
                    "accessKeyId": "AKIA",
                    "secretAccessKey": "secret",
                },
                "content_hash": "abc123",
                "cred_version": "1",
                "auth_mode": "explicit_keys",
            }
        return None

    db._fetch_one.side_effect = fetch
    reader = ResourceProfileReader(db)
    h5 = reader.h5_storage_defaults("epimethyl-samples")
    assert h5 is not None
    assert h5["bucket"] == "epimethyl"
    assert h5["credentials"]["secretAccessKey"] == "secret"
    assert h5["contentHash"] == "abc123"
    assert h5["credentialName"] == "epimethyl-archive-keys"
    assert h5["prefixBase"] == "samples/"
    assert "prefix" not in h5 or h5.get("prefix") in (None, "")


def test_resource_profile_reader_missing_credential_raises() -> None:
    """Named credential_name with no published secret must not ambient-fallback."""
    db = MagicMock()
    db.backend = "postgres"

    def fetch(sql: str, params: tuple = ()):
        if "portal.resource_profile" in sql:
            return {
                "profile_key": "epimethyl-samples",
                "profile_type": "cfg_storage_endpoint_ref",
                "profile_json": {"sampleStorageEndpoint": "epimethyl-archive"},
                "status": "ACTIVE",
            }
        if "cfg.storage_endpoint" in sql:
            return {
                "location_json": {
                    "type": "s3",
                    "bucket": "epimethyl",
                    "region": "us-east-1",
                },
                "provider": "s3",
                "credential_name": "missing-keys",
                "endpoint_version": "1",
                "secret_json": None,
                "content_hash": None,
                "cred_version": None,
                "auth_mode": None,
            }
        return None

    db._fetch_one.side_effect = fetch
    reader = ResourceProfileReader(db)
    with pytest.raises(KeyError, match="credential not found: missing-keys"):
        reader.h5_storage_defaults("epimethyl-samples")


def test_expanded_archive_defaults_validate_as_sample_storage() -> None:
    """P0 fix: ResourceProfileReader output must pass SamplePrepPlanRequest storage models."""
    from methyl_domain.sample_storage import SampleStorageDefaults
    from pydantic import TypeAdapter

    db = MagicMock()
    db.backend = "postgres"

    def fetch(sql: str, params: tuple = ()):
        if "portal.resource_profile" in sql:
            return {
                "profile_key": "epimethyl-samples",
                "profile_type": "cfg_storage_endpoint_ref",
                "profile_json": {
                    "sampleStorageEndpoint": "epimethyl-archive",
                    "prefixBase": "samples/",
                    "scope": "archive",
                },
                "status": "ACTIVE",
            }
        if "cfg.storage_endpoint" in sql:
            return {
                "location_json": {
                    "type": "s3",
                    "bucket": "epimethyl",
                    "region": "us-east-1",
                    "endpointUrl": "https://s3.us-east-1.myqnapcloud.io",
                    "scope": "archive",
                    "prefixBase": "samples/",
                },
                "provider": "s3",
                "credential_name": "epimethyl-archive-keys",
                "endpoint_version": "1",
                "secret_json": {
                    "authMode": "explicit_keys",
                    "accessKeyId": "AKIA",
                    "secretAccessKey": "secret",
                },
                "content_hash": "abc123",
                "cred_version": "1",
                "auth_mode": "explicit_keys",
            }
        return None

    db._fetch_one.side_effect = fetch
    reader = ResourceProfileReader(db)
    h5 = reader.h5_storage_defaults("epimethyl-samples")
    assert h5 is not None
    model = TypeAdapter(SampleStorageDefaults).validate_python(h5)
    assert model.contentHash == "abc123"
    assert model.credentialName == "epimethyl-archive-keys"
    assert model.scope == "archive"
    assert model.prefixBase == "samples/"


def test_download_and_archive_task_inputs_accept_expanded_locations() -> None:
    from methyl_worker.task_models.sample_prep_models import (
        ArchiveSampleTaskInput,
        DownloadFastqTaskInput,
    )

    source = {
        "type": "s3",
        "bucket": "cohort",
        "prefix": "S1/",
        "credentialName": "lab-keys",
        "contentHash": "hash1",
        "credentials": {
            "authMode": "explicit_keys",
            "accessKeyId": "AKIA",
            "secretAccessKey": "sec",
            "credentialName": "lab-keys",
            "contentHash": "hash1",
        },
    }
    dl = DownloadFastqTaskInput(
        sampleId="S1",
        sampleDir="/work/samples/S1",
        fastqSource=source,
    )
    assert dl.fastqSource.contentHash == "hash1"

    dest = {
        "type": "s3",
        "bucket": "epimethyl",
        "prefix": "samples/S1/",
        "scope": "archive",
        "credentialName": "archive-keys",
        "contentHash": "hash2",
        "credentials": {
            "authMode": "explicit_keys",
            "accessKeyId": "AKIA",
            "secretAccessKey": "sec",
            "contentHash": "hash2",
        },
    }
    ar = ArchiveSampleTaskInput(
        sampleId="S1",
        sampleDir="/work/samples/S1",
        sampleDestination=dest,
    )
    assert ar.sampleDestination.contentHash == "hash2"
    assert ar.sampleDestination.scope == "archive"
