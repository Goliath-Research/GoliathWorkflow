"""Tests for sample.archive_sample and legacy sample.upload_h5."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from methyl_domain.sample_storage import SampleDestinationLocation
from methyl_worker.handlers import execute_task
from methyl_worker.sample_archive import _should_skip_azure, archive_sample, upload_h5_files
from pydantic import TypeAdapter

_DEST_ADAPTER = TypeAdapter(SampleDestinationLocation)


def _dest(raw: dict) -> SampleDestinationLocation:
    return _DEST_ADAPTER.validate_python(raw)


def test_archive_sample_full_file_destination(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    archive_root = tmp_path / "archive"
    h5 = sample_dir / "1-CG.h5"
    h5.write_bytes(b"h5-data")
    (sample_dir / "S1_1.fastq.gz").write_bytes(b"fq")
    (sample_dir / "S1.extraction_qc.json").write_text("{}", encoding="utf-8")

    dest = _dest({"type": "file", "basePath": str(archive_root), "prefix": "S1/"})
    first = archive_sample(
        sample_dir=sample_dir,
        sample_id="S1",
        sample_destination=dest,
        mode="full",
    )
    assert first["uploadedCount"] >= 2
    assert (archive_root / "S1" / "h5" / "1-CG.h5").read_bytes() == b"h5-data"
    assert (archive_root / "S1" / "fastq" / "S1_1.fastq.gz").is_file()

    second = archive_sample(
        sample_dir=sample_dir,
        sample_id="S1",
        sample_destination=dest,
        mode="full",
    )
    assert second["skippedCount"] >= 1


def test_archive_sample_qc_only(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    archive_root = tmp_path / "archive"
    (sample_dir / "S1.json").write_text('{"guardrails": {}}', encoding="utf-8")
    (sample_dir / "S1_1.fastq.gz").write_bytes(b"fq")

    dest = _dest({"type": "file", "basePath": str(archive_root), "prefix": "S1/"})
    result = archive_sample(
        sample_dir=sample_dir,
        sample_id="S1",
        sample_destination=dest,
        mode="qc_only",
        reject_reason="alignment_qc_failed",
    )
    assert result["archiveMode"] == "qc_only"
    assert (archive_root / "S1" / "qc" / "alignment.json").is_file()
    assert not (archive_root / "S1" / "fastq").exists()


def test_upload_h5_handler_file_destination(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    archive_root = tmp_path / "archive"
    (sample_dir / "1-CG.h5").write_bytes(b"h5")

    out = execute_task(
        "sample.upload-h5",
        "sample.upload_h5",
        {
            "sampleId": "S1",
            "sampleDir": str(sample_dir),
            "sampleDestination": {
                "type": "file",
                "basePath": str(archive_root),
                "prefix": "S1/",
            },
            "h5Files": ["1-CG.h5"],
        },
    )
    assert out["uploadedCount"] >= 1
    assert (archive_root / "S1" / "h5" / "1-CG.h5").is_file()


def test_upload_h5_s3_skips_unchanged(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    local = sample_dir / "1-CG.h5"
    payload = b"x" * 64
    local.write_bytes(payload)
    etag = hashlib.md5(payload).hexdigest()

    mock_client = MagicMock()
    mock_client.head_object.return_value = {
        "ContentLength": len(payload),
        "ETag": f'"{etag}"',
    }

    with patch("methyl_worker.sample_archive._s3_client", return_value=mock_client):
        dest = _dest(
            {
                "type": "s3",
                "bucket": "archive",
                "prefix": "S1/",
                "region": "us-east-1",
                "credentials": {"authMode": "instance_profile"},
            }
        )
        result = upload_h5_files(sample_dir=sample_dir, h5_destination=dest)

    assert result["skippedCount"] >= 1 or result["uploadedCount"] == 1
    uploaded_keys = [call.args[2] for call in mock_client.upload_file.call_args_list]
    assert not any("/h5/" in key or key.endswith(".h5") for key in uploaded_keys)


def test_should_skip_azure_matches_content_md5_bytes(tmp_path: Path) -> None:
    local = tmp_path / "1-CG.h5"
    payload = b"azure-md5-payload"
    local.write_bytes(payload)

    content_settings = MagicMock()
    content_settings.content_md5 = __import__("hashlib").md5(payload).digest()
    props = MagicMock(size=len(payload), content_settings=content_settings)
    blob_client = MagicMock()
    blob_client.get_blob_properties.return_value = props

    assert _should_skip_azure(blob_client, local) is True
    blob_client.upload_blob.assert_not_called()


def test_upload_h5_missing_files_raises(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    dest = _dest({"type": "file", "basePath": str(tmp_path / "archive"), "prefix": "S1/"})
    with pytest.raises(RuntimeError, match="HDF5 file not found"):
        upload_h5_files(sample_dir=sample_dir, h5_destination=dest, h5_files=["missing.h5"])
