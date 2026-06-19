"""Download per-sample FASTQ folders from structured file, S3, or Azure Blob sources."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Sequence

from methyl_domain.fastq_storage import (
    AzureFastqSource,
    FastqSourceLocation,
    FileFastqSource,
    S3ExplicitKeysCredentials,
    S3FastqSource,
    resolve_file_local_root,
)

logger = logging.getLogger(__name__)

FASTQ_GLOB_PATTERNS: Sequence[str] = ("*.fastq.gz", "*.fq.gz", "*.fastq", "*.fq")
FASTQ_SUFFIXES: Sequence[str] = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
_MTIME_TOLERANCE_S = 1.0


@dataclass(frozen=True)
class RemoteObject:
    """Remote FASTQ object metadata used for idempotent download decisions."""

    name: str
    size: int
    mtime: float
    locator: str = ""


@dataclass(frozen=True)
class FastqSource:
    scheme: str
    bucket: str = ""
    container: str = ""
    account: str = ""
    prefix: str = ""
    local_root: Path | None = None
    s3_source: S3FastqSource | None = None
    azure_source: AzureFastqSource | None = None


@dataclass
class _CloudClients:
    """Reused authenticated clients for one ``download_from_source`` invocation."""

    s3: Any = field(default=None, repr=False)
    azure: Any = field(default=None, repr=False)


def _matches_fastq(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in FASTQ_SUFFIXES)


def _is_folder_uri(key_or_prefix: str) -> bool:
    if key_or_prefix.endswith("/"):
        return True
    leaf = key_or_prefix.rsplit("/", 1)[-1]
    return not _matches_fastq(leaf)


def _should_skip_download(local: Path, remote_size: int, remote_mtime: float) -> bool:
    if not local.is_file():
        return False
    stat = local.stat()
    if stat.st_size != remote_size:
        return False
    return abs(stat.st_mtime - remote_mtime) <= _MTIME_TOLERANCE_S


def _touch_mtime(local: Path, remote_mtime: float) -> None:
    os.utime(local, (remote_mtime, remote_mtime))


def _dt_to_mtime(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _basename_from_key(key: str) -> str:
    return key.rstrip("/").rsplit("/", 1)[-1]


def _relative_to_prefix(key: str, prefix: str) -> str:
    normalized_key = key.rstrip("/")
    list_prefix = prefix
    if list_prefix and not list_prefix.endswith("/"):
        list_prefix += "/"
    if list_prefix and normalized_key.startswith(list_prefix):
        relative = normalized_key[len(list_prefix) :]
        if relative:
            return relative
    return _basename_from_key(normalized_key)


def download_from_source(source: FastqSourceLocation, dest_dir: Path) -> List[str]:
    """Copy or download all FASTQs for one sample into ``dest_dir``."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    runtime = _runtime_source_from_model(source)
    clients = _CloudClients()
    objects = _list_objects(runtime, clients)
    if not objects:
        raise RuntimeError(f"No FASTQ files found at {source.model_dump(mode='json')}")

    paths: List[str] = []
    for obj in sorted(objects, key=lambda item: item.name):
        target = dest_dir / obj.name
        if _should_skip_download(target, obj.size, obj.mtime):
            logger.info("Skipping unchanged FASTQ %s", target)
        else:
            _fetch_object(runtime, obj, target, clients)
            _touch_mtime(target, obj.mtime)
        paths.append(str(target))
    return paths


def _runtime_source_from_model(source: FastqSourceLocation) -> FastqSource:
    if isinstance(source, FileFastqSource):
        local_root = resolve_file_local_root(source)
        return FastqSource(
            scheme="file",
            prefix=source.prefix,
            local_root=local_root,
        )
    if isinstance(source, S3FastqSource):
        return FastqSource(
            scheme="s3",
            bucket=source.bucket,
            prefix=source.prefix,
            s3_source=source,
        )
    if isinstance(source, AzureFastqSource):
        return FastqSource(
            scheme="az",
            account=source.account,
            container=source.container,
            prefix=source.prefix,
            azure_source=source,
        )
    raise RuntimeError(f"Unsupported fastq source type: {type(source)!r}")


def _list_objects(source: FastqSource, clients: _CloudClients) -> List[RemoteObject]:
    if source.scheme == "file":
        return _list_local_objects(source)
    if source.scheme == "s3":
        return _list_s3_objects(source, clients)
    if source.scheme == "az":
        return _list_azure_objects(source, clients)
    raise RuntimeError(f"Unsupported source scheme {source.scheme!r}")


def _list_local_objects(source: FastqSource) -> List[RemoteObject]:
    root = source.local_root
    if root is None:
        raise RuntimeError("local FASTQ source is missing local_root")

    if root.is_file():
        if not _matches_fastq(root.name):
            raise RuntimeError(f"Source is not a FASTQ file: {root}")
        stat = root.stat()
        return [RemoteObject(name=root.name, size=stat.st_size, mtime=stat.st_mtime, locator=root.name)]

    if not root.is_dir():
        raise RuntimeError(f"fastq source not found: {root}")

    objects: List[RemoteObject] = []
    for pattern in FASTQ_GLOB_PATTERNS:
        for match in sorted(root.glob(pattern)):
            if not match.is_file():
                continue
            stat = match.stat()
            objects.append(
                RemoteObject(name=match.name, size=stat.st_size, mtime=stat.st_mtime, locator=match.name)
            )
    return objects


def _fetch_object(
    source: FastqSource, obj: RemoteObject, target: Path, clients: _CloudClients
) -> None:
    if source.scheme == "file":
        root = source.local_root
        if root is None:
            raise RuntimeError("local FASTQ source is missing local_root")
        src = root / obj.locator if root.is_dir() else root
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        return
    if source.scheme == "s3":
        _download_s3_object(source.bucket, obj.locator, target, clients, source.s3_source)
        return
    if source.scheme == "az":
        _download_azure_object(source, obj.locator, target, clients)
        return
    raise RuntimeError(f"Unsupported source scheme {source.scheme!r}")


def _s3_client(source: S3FastqSource):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for s3 fastqSource; install methyl-worker with cloud dependencies"
        ) from exc

    client_kwargs: dict[str, Any] = {}
    if source.endpointUrl:
        client_kwargs["endpoint_url"] = source.endpointUrl
    if source.region:
        client_kwargs["region_name"] = source.region

    creds = source.credentials
    if creds.authMode == "explicit_keys":
        assert isinstance(creds, S3ExplicitKeysCredentials)
        session_token = creds.sessionToken.get_secret_value() if creds.sessionToken else None
        return boto3.client(
            "s3",
            aws_access_key_id=creds.accessKeyId,
            aws_secret_access_key=creds.secretAccessKey.get_secret_value(),
            aws_session_token=session_token,
            **client_kwargs,
        )
    return boto3.client("s3", **client_kwargs)


def _list_s3_objects(source: FastqSource, clients: _CloudClients) -> List[RemoteObject]:
    if source.s3_source is None:
        raise RuntimeError("S3 fastq source missing typed configuration")
    prefix = source.prefix
    if clients.s3 is None:
        clients.s3 = _s3_client(source.s3_source)
    client = clients.s3

    if not _is_folder_uri(prefix):
        response = client.head_object(Bucket=source.bucket, Key=prefix)
        if not _matches_fastq(prefix):
            raise RuntimeError(f"S3 object is not a FASTQ file: s3://{source.bucket}/{prefix}")
        return [
            RemoteObject(
                name=_basename_from_key(prefix),
                size=int(response["ContentLength"]),
                mtime=_dt_to_mtime(response["LastModified"]),
                locator=prefix,
            )
        ]

    list_prefix = prefix if prefix.endswith("/") else f"{prefix}/"

    objects: List[RemoteObject] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=source.bucket, Prefix=list_prefix):
        for item in page.get("Contents", []):
            key = str(item["Key"])
            if key.endswith("/") or not _matches_fastq(key):
                continue
            objects.append(
                RemoteObject(
                    name=_relative_to_prefix(key, list_prefix),
                    size=int(item["Size"]),
                    mtime=_dt_to_mtime(item["LastModified"]),
                    locator=key,
                )
            )
    return objects


def _download_s3_object(
    bucket: str,
    key: str,
    target: Path,
    clients: _CloudClients,
    s3_source: S3FastqSource | None,
) -> None:
    if clients.s3 is None:
        if s3_source is None:
            raise RuntimeError("S3 download requires typed s3_source")
        clients.s3 = _s3_client(s3_source)
    target.parent.mkdir(parents=True, exist_ok=True)
    clients.s3.download_file(bucket, key, str(target))


def _azure_blob_service(source: AzureFastqSource):
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(
            "azure-identity and azure-storage-blob are required for azure_blob fastqSource"
        ) from exc

    creds = source.credentials
    if creds.authMode == "connection_string":
        return BlobServiceClient.from_connection_string(creds.connectionString.get_secret_value())
    if creds.authMode == "account_key":
        account_url = f"https://{source.account}.blob.core.windows.net"
        return BlobServiceClient(account_url, credential=creds.accountKey.get_secret_value())
    account_url = f"https://{source.account}.blob.core.windows.net"
    return BlobServiceClient(account_url, credential=DefaultAzureCredential())


def _list_azure_objects(source: FastqSource, clients: _CloudClients) -> List[RemoteObject]:
    if source.azure_source is None:
        raise RuntimeError("Azure fastq source missing typed configuration")
    if clients.azure is None:
        clients.azure = _azure_blob_service(source.azure_source)
    service = clients.azure
    container_client = service.get_container_client(source.container)
    prefix = source.prefix

    if not _is_folder_uri(prefix):
        blob_client = container_client.get_blob_client(prefix)
        props = blob_client.get_blob_properties()
        if not _matches_fastq(prefix):
            raise RuntimeError(
                f"Azure blob is not a FASTQ file: {source.account}@{source.container}/{prefix}"
            )
        return [
            RemoteObject(
                name=_basename_from_key(prefix),
                size=int(props.size),
                mtime=_dt_to_mtime(props.last_modified),
                locator=prefix,
            )
        ]

    list_prefix = prefix if prefix.endswith("/") else f"{prefix}/"

    objects: List[RemoteObject] = []
    for blob in container_client.list_blobs(name_starts_with=list_prefix):
        name = blob.name
        if name.endswith("/") or not _matches_fastq(name):
            continue
        objects.append(
            RemoteObject(
                name=_relative_to_prefix(name, list_prefix),
                size=int(blob.size),
                mtime=_dt_to_mtime(blob.last_modified),
                locator=name,
            )
        )
    return objects


def _download_azure_object(
    source: FastqSource, blob_name: str, target: Path, clients: _CloudClients
) -> None:
    if source.azure_source is None:
        raise RuntimeError("Azure fastq source missing typed configuration")
    if clients.azure is None:
        clients.azure = _azure_blob_service(source.azure_source)
    blob_client = clients.azure.get_blob_client(container=source.container, blob=blob_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as handle:
        blob_client.download_blob().readinto(handle)
