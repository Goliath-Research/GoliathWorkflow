"""Tests for sample.upload_h5 archive copy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from methyl_worker.handlers import execute_task
from methyl_worker.h5_upload import _should_skip_azure, upload_h5_files
from pydantic import TypeAdapter
from methyl_domain.h5_storage import H5DestinationLocation

_DEST_ADAPTER = TypeAdapter(H5DestinationLocation)


def _dest(raw: dict) -> H5DestinationLocation:
    return _DEST_ADAPTER.validate_python(raw)


def test_upload_h5_file_destination_copies_and_skips(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    archive_root = tmp_path / "archive"
    h5 = sample_dir / "1-CG.h5"
    h5.write_bytes(b"h5-data")

    dest = _dest({"type": "file", "basePath": str(archive_root), "prefix": "S1/"})
    first = upload_h5_files(sample_dir=sample_dir, h5_destination=dest)
    assert first["uploadedCount"] == 1
    assert first["uploadedFiles"] == ["1-CG.h5"]
    assert (archive_root / "S1" / "1-CG.h5").read_bytes() == b"h5-data"

    second = upload_h5_files(sample_dir=sample_dir, h5_destination=dest)
    assert second["skippedCount"] == 1
    assert second["uploadedCount"] == 0


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
            "h5Destination": {
                "type": "file",
                "basePath": str(archive_root),
                "prefix": "S1/",
            },
            "h5Files": ["1-CG.h5"],
        },
    )
    assert out["uploadedCount"] == 1
    assert (archive_root / "S1" / "1-CG.h5").is_file()


def test_upload_h5_s3_skips_unchanged(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    local = sample_dir / "1-CG.h5"
    local.write_bytes(b"x" * 64)

    mock_client = MagicMock()
    mock_client.head_object.return_value = {
        "ContentLength": 64,
        "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
    }

    with patch("methyl_worker.h5_upload._s3_client", return_value=mock_client):
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

    assert result["skippedCount"] == 1
    mock_client.upload_file.assert_not_called()


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
    with pytest.raises(RuntimeError, match="HDF5 files not found"):
        upload_h5_files(sample_dir=sample_dir, h5_destination=dest, h5_files=["missing.h5"])
