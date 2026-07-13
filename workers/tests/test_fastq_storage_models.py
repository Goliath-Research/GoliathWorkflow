"""Tests for structured FASTQ storage models."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from methyl_domain.fastq_storage import (
    FastqSourceLocation,
    FastqStorageDefaults,
    FileFastqStorageDefaults,
    S3FastqStorageDefaults,
    merge_fastq_source,
    normalize_sample_prefix,
)


def test_normalize_sample_prefix() -> None:
    assert normalize_sample_prefix("plasma/S1") == "plasma/S1/"
    assert normalize_sample_prefix("plasma/S1/") == "plasma/S1/"
    assert normalize_sample_prefix("/plasma/S1/") == "plasma/S1/"


def test_merge_file_storage() -> None:
    defaults = FileFastqStorageDefaults(basePath="/work/fastq")
    source = merge_fastq_source(defaults, "S1")
    assert source.type == "file"
    assert source.basePath == "/work/fastq"
    assert source.prefix == "S1/"


def test_merge_s3_vault_credentials() -> None:
    defaults = S3FastqStorageDefaults(
        bucket="epimethyl",
        endpointUrl="https://s3.us-east-1.myqnapcloud.io",
        credentials={
            "authMode": "azure_key_vault",
            "vaultUrl": "https://kv.vault.azure.net/",
            "secretName": "epimethyl-s3",
        },
    )
    source = merge_fastq_source(defaults, "S1")
    assert source.credentials.authMode == "azure_key_vault"
    assert source.credentials.secretName == "epimethyl-s3"


def test_merge_s3_storage() -> None:
    defaults = S3FastqStorageDefaults(
        bucket="cohort",
        credentials={"authMode": "instance_profile"},
    )
    source = merge_fastq_source(defaults, "plasma/S1")
    assert source.bucket == "cohort"
    assert source.prefix == "plasma/S1/"


def test_dump_storage_model_reveals_explicit_keys() -> None:
    from methyl_domain.fastq_storage import S3ExplicitKeysCredentials, dump_storage_model
    from methyl_domain.h5_storage import S3H5StorageDefaults

    model = S3H5StorageDefaults(
        bucket="epimethyl",
        prefixBase="samples/",
        credentials=S3ExplicitKeysCredentials(
            accessKeyId="AKIA",
            secretAccessKey="real-secret",
        ),
    )
    dumped = dump_storage_model(model)
    assert dumped["credentials"]["secretAccessKey"] == "real-secret"
    assert dumped["credentials"]["secretAccessKey"] != "**********"


def test_s3_explicit_keys_require_secret() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(FastqStorageDefaults).validate_python(
            {
                "type": "s3",
                "bucket": "b",
                "credentials": {"authMode": "explicit_keys", "accessKeyId": "AKIA"},
            }
        )


def test_fastq_source_discriminator() -> None:
    source = TypeAdapter(FastqSourceLocation).validate_python(
        {
            "type": "file",
            "basePath": "/data",
            "prefix": "S1/",
        }
    )
    assert source.prefix == "S1/"
