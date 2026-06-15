"""Download per-sample FASTQ folders from file, S3, or Azure Blob sources."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence
from urllib.parse import urlparse

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


def download_fastqs(source_uri: str, dest_dir: Path) -> List[str]:
    """Copy or download all FASTQs for one sample into ``dest_dir``."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = _parse_source(source_uri)
    objects = _list_objects(source)
    if not objects:
        raise RuntimeError(f"No FASTQ files found at {source_uri}")

    paths: List[str] = []
    for obj in sorted(objects, key=lambda item: item.name):
        target = dest_dir / obj.name
        if _should_skip_download(target, obj.size, obj.mtime):
            logger.info("Skipping unchanged FASTQ %s", target)
        else:
            _fetch_object(source, obj, target)
            _touch_mtime(target, obj.mtime)
        paths.append(str(target))
    return paths


def _parse_source(source_uri: str) -> FastqSource:
    parsed = urlparse(str(source_uri))
    scheme = (parsed.scheme or "file").lower()

    if scheme in {"file", ""}:
        src_path = Path(parsed.path if parsed.scheme == "file" else str(source_uri))
        if src_path.is_file():
            return FastqSource(scheme="file", prefix=src_path.name, local_root=src_path)
        return FastqSource(scheme="file", prefix="", local_root=src_path)

    if scheme == "s3":
        bucket = parsed.netloc
        if not bucket:
            raise RuntimeError("s3:// URI requires a bucket name")
        return FastqSource(scheme="s3", bucket=bucket, prefix=parsed.path.lstrip("/"))

    if scheme == "az":
        account, container, prefix = _parse_azure_uri(parsed)
        return FastqSource(
            scheme="az",
            account=account,
            container=container,
            prefix=prefix,
        )

    raise RuntimeError(
        f"Unsupported fastqSourceUri scheme {scheme!r}; use file://, s3://, or az://."
    )


def _parse_azure_uri(parsed) -> tuple[str, str, str]:
    netloc = parsed.netloc
    if "@" in netloc:
        account, container = netloc.split("@", 1)
        if not account or not container:
            raise RuntimeError("az://account@container/... URI is malformed")
        return account, container, parsed.path.lstrip("/")

    if not netloc:
        raise RuntimeError("az:// URI requires a container name")

    account = os.environ.get("AZURE_STORAGE_ACCOUNT", "").strip()
    if not account:
        raise RuntimeError(
            "AZURE_STORAGE_ACCOUNT is required for az://container/prefix URIs "
            "(or use az://account@container/prefix)"
        )
    return account, netloc, parsed.path.lstrip("/")


def _list_objects(source: FastqSource) -> List[RemoteObject]:
    if source.scheme == "file":
        return _list_local_objects(source)
    if source.scheme == "s3":
        return _list_s3_objects(source)
    if source.scheme == "az":
        return _list_azure_objects(source)
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


def _fetch_object(source: FastqSource, obj: RemoteObject, target: Path) -> None:
    if source.scheme == "file":
        root = source.local_root
        if root is None:
            raise RuntimeError("local FASTQ source is missing local_root")
        src = root / obj.locator if root.is_dir() else root
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        return
    if source.scheme == "s3":
        _download_s3_object(source.bucket, obj.locator, target)
        return
    if source.scheme == "az":
        _download_azure_object(source.account, source.container, obj.locator, target)
        return
    raise RuntimeError(f"Unsupported source scheme {source.scheme!r}")


def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for s3:// fastqSourceUri; install methyl-worker with cloud dependencies"
        ) from exc

    endpoint_url = os.environ.get("METHYL_S3_ENDPOINT_URL")
    region_name = os.environ.get("METHYL_S3_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    access_key = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("METHYL_S3_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("METHYL_S3_SECRET_ACCESS_KEY")
    session_token = os.environ.get("AWS_SESSION_TOKEN") or os.environ.get("METHYL_S3_SESSION_TOKEN")

    client_kwargs = {}
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    if region_name:
        client_kwargs["region_name"] = region_name

    if access_key and secret_key:
        return boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            **client_kwargs,
        )
    if session_token:
        raise RuntimeError(
            "AWS_SESSION_TOKEN (or METHYL_S3_SESSION_TOKEN) requires access key and secret key"
        )
    return boto3.client("s3", **client_kwargs)


def _list_s3_objects(source: FastqSource) -> List[RemoteObject]:
    prefix = source.prefix
    client = _s3_client()

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

    list_prefix = prefix
    if list_prefix and not list_prefix.endswith("/"):
        list_prefix += "/"

    objects: List[RemoteObject] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=source.bucket, Prefix=list_prefix):
        for item in page.get("Contents", []):
            key = str(item["Key"])
            if key.endswith("/") or not _matches_fastq(key):
                continue
            objects.append(
                RemoteObject(
                    name=_basename_from_key(key),
                    size=int(item["Size"]),
                    mtime=_dt_to_mtime(item["LastModified"]),
                    locator=key,
                )
            )
    return objects


def _download_s3_object(bucket: str, key: str, target: Path) -> None:
    client = _s3_client()
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, key, str(target))


def _azure_blob_service(account: str):
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(
            "azure-identity and azure-storage-blob are required for az:// fastqSourceUri"
        ) from exc

    account_url = f"https://{account}.blob.core.windows.net"
    return BlobServiceClient(account_url, credential=DefaultAzureCredential())


def _list_azure_objects(source: FastqSource) -> List[RemoteObject]:
    service = _azure_blob_service(source.account)
    container_client = service.get_container_client(source.container)
    prefix = source.prefix

    if not _is_folder_uri(prefix):
        blob_client = container_client.get_blob_client(prefix)
        props = blob_client.get_blob_properties()
        if not _matches_fastq(prefix):
            raise RuntimeError(
                f"Azure blob is not a FASTQ file: az://{source.account}@{source.container}/{prefix}"
            )
        return [
            RemoteObject(
                name=_basename_from_key(prefix),
                size=int(props.size),
                mtime=_dt_to_mtime(props.last_modified),
                locator=prefix,
            )
        ]

    list_prefix = prefix
    if list_prefix and not list_prefix.endswith("/"):
        list_prefix += "/"

    objects: List[RemoteObject] = []
    for blob in container_client.list_blobs(name_starts_with=list_prefix):
        name = blob.name
        if name.endswith("/") or not _matches_fastq(name):
            continue
        objects.append(
            RemoteObject(
                name=_basename_from_key(name),
                size=int(blob.size),
                mtime=_dt_to_mtime(blob.last_modified),
                locator=name,
            )
        )
    return objects


def _download_azure_object(account: str, container: str, blob_name: str, target: Path) -> None:
    service = _azure_blob_service(account)
    blob_client = service.get_blob_client(container=container, blob=blob_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as handle:
        blob_client.download_blob().readinto(handle)
