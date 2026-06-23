"""
Resolve platform **archive** storage from database rows into planner JSON.

Maps ``wf.platform_sample_storage`` rows to ``h5Storage`` (and future retention
upload actions). Initial FASTQ ingress always uses laboratory ``fastqStorage``
from the study start request — never from this table.
"""

from __future__ import annotations

from typing import Any, Mapping

from .fastq_storage import FastqStorageDefaults, S3FastqStorageDefaults, S3ExplicitKeysCredentials
from .h5_storage import H5StorageDefaults, S3H5StorageDefaults


DEFAULT_STORAGE_KEY = "epimethyl-samples"


def normalize_s3_endpoint_url(endpoint_url: str) -> str:
    url = str(endpoint_url).strip()
    if not url:
        raise ValueError("endpoint_url is required")
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url


def sample_prefix_from_base(base_prefix: str, sample_id: str) -> str:
    """Build per-sample prefix under a platform base (e.g. samples/S1/)."""
    base = str(base_prefix).strip().strip("/")
    sid = str(sample_id).strip().strip("/")
    if not base:
        return f"{sid}/"
    return f"{base}/{sid}/"


def platform_row_to_s3_defaults(row: Mapping[str, Any]) -> S3FastqStorageDefaults:
    return S3FastqStorageDefaults(
        bucket=str(row["bucket"]),
        region=(str(row["region"]) if row.get("region") else None),
        endpointUrl=normalize_s3_endpoint_url(str(row["endpoint_url"])),
        prefixBase=str(row.get("base_prefix") or "samples/"),
        credentials=S3ExplicitKeysCredentials(
            accessKeyId=str(row["access_key_id"]),
            secretAccessKey=str(row["secret_access_key"]),
        ),
    )


def platform_row_to_fastq_storage(row: Mapping[str, Any]) -> FastqStorageDefaults:
    provider = str(row.get("provider_type") or "s3").lower()
    if provider != "s3":
        raise ValueError(f"unsupported platform sample storage provider: {provider}")
    return platform_row_to_s3_defaults(row)


def platform_row_to_h5_storage(row: Mapping[str, Any]) -> H5StorageDefaults:
    provider = str(row.get("provider_type") or "s3").lower()
    if provider != "s3":
        raise ValueError(f"unsupported platform sample storage provider: {provider}")
    s3 = platform_row_to_s3_defaults(row)
    return S3H5StorageDefaults(
        bucket=s3.bucket,
        region=s3.region,
        endpointUrl=s3.endpointUrl,
        prefixBase=s3.prefixBase,
        credentials=s3.credentials,
    )
