"""
Structured HDF5 archive destinations for Portal JSON and upload workers.

Instance-level ``H5StorageDefaults`` plus per-sample ``prefix`` merge into
``H5DestinationLocation`` on each upload task.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .fastq_storage import (
    AzureCredentials,
    S3Credentials,
    normalize_sample_prefix,
    resolve_sample_storage_prefix,
)

# Re-export credential types for object storage symmetry.
__all__ = [
    "H5StorageDefaults",
    "H5DestinationLocation",
    "merge_h5_destination",
    "resolve_file_local_root",
]


class FileH5StorageDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["file"] = "file"
    basePath: str


class S3H5StorageDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["s3"] = "s3"
    bucket: str
    region: str | None = None
    endpointUrl: str | None = None
    prefixBase: str | None = None
    credentials: S3Credentials


class AzureH5StorageDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["azure_blob"] = "azure_blob"
    account: str
    container: str
    credentials: AzureCredentials


H5StorageDefaults = Annotated[
    Union[FileH5StorageDefaults, S3H5StorageDefaults, AzureH5StorageDefaults],
    Field(discriminator="type"),
]


class FileH5Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["file"] = "file"
    basePath: str
    prefix: str = ""

    @model_validator(mode="after")
    def _normalize_prefix(self) -> FileH5Destination:
        if self.prefix:
            object.__setattr__(self, "prefix", normalize_sample_prefix(self.prefix))
        return self


class S3H5Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["s3"] = "s3"
    bucket: str
    prefix: str
    region: str | None = None
    endpointUrl: str | None = None
    credentials: S3Credentials

    @model_validator(mode="after")
    def _normalize_prefix(self) -> S3H5Destination:
        object.__setattr__(self, "prefix", normalize_sample_prefix(self.prefix))
        return self


class AzureH5Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["azure_blob"] = "azure_blob"
    account: str
    container: str
    prefix: str
    credentials: AzureCredentials

    @model_validator(mode="after")
    def _normalize_prefix(self) -> AzureH5Destination:
        object.__setattr__(self, "prefix", normalize_sample_prefix(self.prefix))
        return self


H5DestinationLocation = Annotated[
    Union[FileH5Destination, S3H5Destination, AzureH5Destination],
    Field(discriminator="type"),
]


def merge_h5_destination(defaults: H5StorageDefaults, prefix: str) -> H5DestinationLocation:
    """Materialize per-sample destination from instance defaults and sample prefix."""
    norm = normalize_sample_prefix(prefix)
    if isinstance(defaults, FileH5StorageDefaults):
        return FileH5Destination(basePath=defaults.basePath, prefix=norm)
    if isinstance(defaults, S3H5StorageDefaults):
        return S3H5Destination(
            bucket=defaults.bucket,
            prefix=norm,
            region=defaults.region,
            endpointUrl=defaults.endpointUrl,
            credentials=defaults.credentials,
        )
    if isinstance(defaults, AzureH5StorageDefaults):
        return AzureH5Destination(
            account=defaults.account,
            container=defaults.container,
            prefix=norm,
            credentials=defaults.credentials,
        )
    raise TypeError(f"unsupported h5 storage defaults: {type(defaults)!r}")


def resolve_file_local_root(destination: FileH5Destination) -> Path:
    base = Path(destination.basePath).expanduser()
    if not destination.prefix:
        return base
    return base / destination.prefix.rstrip("/")
