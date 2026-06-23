"""Tests for platform sample storage resolution."""

from __future__ import annotations

from methyl_domain.platform_storage import (
    DEFAULT_STORAGE_KEY,
    normalize_s3_endpoint_url,
    platform_row_to_fastq_storage,
    platform_row_to_h5_storage,
)
from methyl_domain.fastq_storage import resolve_sample_storage_prefix


def test_normalize_s3_endpoint_url_adds_https() -> None:
    assert normalize_s3_endpoint_url("s3.us-east-1.myqnapcloud.io") == (
        "https://s3.us-east-1.myqnapcloud.io"
    )


def test_platform_row_builds_myqnap_defaults() -> None:
    row = {
        "storage_key": DEFAULT_STORAGE_KEY,
        "provider_type": "s3",
        "bucket": "epimethyl",
        "region": "us-east-1",
        "endpoint_url": "s3.us-east-1.myqnapcloud.io",
        "access_key_id": "AKIATEST",
        "secret_access_key": "secret",
        "base_prefix": "samples/",
        "status": "ACTIVE",
    }
    fastq = platform_row_to_fastq_storage(row)
    h5 = platform_row_to_h5_storage(row)
    assert fastq.bucket == "epimethyl"
    assert fastq.endpointUrl == "https://s3.us-east-1.myqnapcloud.io"
    assert fastq.prefixBase == "samples/"
    assert fastq.credentials.accessKeyId == "AKIATEST"
    assert h5.bucket == "epimethyl"
    prefix = resolve_sample_storage_prefix(
        sample_id="S1",
        prefix_base=fastq.prefixBase,
    )
    assert prefix == "samples/S1/"
