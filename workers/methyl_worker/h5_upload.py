"""Upload per-chromosome methylation HDF5 files to object storage (archive copy)."""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

from methyl_domain.fastq_storage import (
    AzureFastqSource,
    S3ExplicitKeysCredentials,
    S3FastqSource,
)
from methyl_domain.h5_storage import (
    AzureH5Destination,
    FileH5Destination,
    H5DestinationLocation,
    S3H5Destination,
    resolve_file_local_root,
)

logger = logging.getLogger(__name__)

H5_SUFFIX = ".h5"


@dataclass(frozen=True)
class UploadTarget:
    scheme: str
    bucket: str = ""
    container: str = ""
    account: str = ""
    prefix: str = ""
    local_root: Path | None = None
    s3_dest: S3H5Destination | None = None
    azure_dest: AzureH5Destination | None = None


@dataclass
class _CloudClients:
    s3: Any = field(default=None, repr=False)
    azure: Any = field(default=None, repr=False)


def _local_h5_files(sample_dir: Path, h5_files: Sequence[str] | None) -> List[Path]:
    if h5_files:
        paths = [sample_dir / name for name in h5_files]
    else:
        paths = sorted(sample_dir.glob(f"*{H5_SUFFIX}"))
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise RuntimeError(f"HDF5 files not found: {', '.join(str(p) for p in missing)}")
    return paths


def _remote_key(prefix: str, filename: str) -> str:
    norm = prefix if prefix.endswith("/") or not prefix else f"{prefix}/"
    return f"{norm}{filename}" if norm else filename


def _file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_skip_s3(client: Any, bucket: str, key: str, local: Path) -> bool:
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except Exception:
        return False
    remote_size = int(head["ContentLength"])
    if local.stat().st_size != remote_size:
        return False
    etag = str(head.get("ETag", "")).strip('"')
    if len(etag) == 32 and etag == _file_md5(local):
        return True
    return remote_size == local.stat().st_size


def _should_skip_azure(blob_client: Any, local: Path) -> bool:
    try:
        props = blob_client.get_blob_properties()
    except Exception:
        return False
    if int(props.size) != local.stat().st_size:
        return False
    content_md5 = getattr(props, "content_settings", None)
    if content_md5 and getattr(content_md5, "content_md5", None):
        import base64

        remote_md5 = base64.b64encode(content_md5.content_md5).decode("ascii")
        if remote_md5 == _file_md5(local):
            return True
    return int(props.size) == local.stat().st_size


def _s3_client(dest: S3H5Destination):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for s3 h5Destination") from exc

    client_kwargs: dict[str, Any] = {}
    if dest.endpointUrl:
        client_kwargs["endpoint_url"] = dest.endpointUrl
    if dest.region:
        client_kwargs["region_name"] = dest.region
    creds = dest.credentials
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


def _azure_service(dest: AzureH5Destination):
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError("azure-storage-blob required for azure_blob h5Destination") from exc

    creds = dest.credentials
    if creds.authMode == "connection_string":
        return BlobServiceClient.from_connection_string(creds.connectionString.get_secret_value())
    if creds.authMode == "account_key":
        account_url = f"https://{dest.account}.blob.core.windows.net"
        return BlobServiceClient(account_url, credential=creds.accountKey.get_secret_value())
    account_url = f"https://{dest.account}.blob.core.windows.net"
    return BlobServiceClient(account_url, credential=DefaultAzureCredential())


def _target_from_model(dest: H5DestinationLocation) -> UploadTarget:
    if isinstance(dest, FileH5Destination):
        return UploadTarget(
            scheme="file",
            prefix=dest.prefix,
            local_root=resolve_file_local_root(dest),
        )
    if isinstance(dest, S3H5Destination):
        return UploadTarget(
            scheme="s3",
            bucket=dest.bucket,
            prefix=dest.prefix,
            s3_dest=dest,
        )
    if isinstance(dest, AzureH5Destination):
        return UploadTarget(
            scheme="az",
            account=dest.account,
            container=dest.container,
            prefix=dest.prefix,
            azure_dest=dest,
        )
    raise RuntimeError(f"Unsupported h5 destination: {type(dest)!r}")


def upload_h5_files(
    *,
    sample_dir: str | Path,
    h5_destination: H5DestinationLocation,
    h5_files: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Archive-copy local HDF5 files to the configured destination."""
    sample_path = Path(sample_dir)
    local_files = _local_h5_files(sample_path, h5_files)
    target = _target_from_model(h5_destination)
    clients = _CloudClients()
    uploaded: List[str] = []
    skipped: List[str] = []

    for local in local_files:
        key = _remote_key(target.prefix, local.name)
        if target.scheme == "file":
            root = target.local_root
            if root is None:
                raise RuntimeError("file h5Destination missing local_root")
            dest_path = root / local.name
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if dest_path.is_file() and dest_path.stat().st_size == local.stat().st_size:
                skipped.append(local.name)
                continue
            shutil.copy2(local, dest_path)
            uploaded.append(local.name)
            continue

        if target.scheme == "s3":
            if clients.s3 is None:
                assert target.s3_dest is not None
                clients.s3 = _s3_client(target.s3_dest)
            if _should_skip_s3(clients.s3, target.bucket, key, local):
                logger.info("Skipping unchanged H5 s3://%s/%s", target.bucket, key)
                skipped.append(local.name)
                continue
            clients.s3.upload_file(str(local), target.bucket, key)
            uploaded.append(local.name)
            continue

        if target.scheme == "az":
            assert target.azure_dest is not None
            if clients.azure is None:
                clients.azure = _azure_service(target.azure_dest)
            blob_client = clients.azure.get_blob_client(container=target.container, blob=key)
            if _should_skip_azure(blob_client, local):
                logger.info("Skipping unchanged H5 %s/%s", target.container, key)
                skipped.append(local.name)
                continue
            with open(local, "rb") as handle:
                blob_client.upload_blob(handle, overwrite=True)
            uploaded.append(local.name)
            continue

        raise RuntimeError(f"Unsupported destination scheme {target.scheme!r}")

    remote_prefix = target.prefix
    return {
        "uploadedFiles": uploaded,
        "skippedFiles": skipped,
        "remotePrefix": remote_prefix,
        "uploadedCount": len(uploaded),
        "skippedCount": len(skipped),
    }


def upload_from_task_input(input_json: Mapping[str, Any]) -> dict[str, Any]:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(H5DestinationLocation)
    dest = adapter.validate_python(input_json["h5Destination"])
    sample_dir = input_json.get("sampleDir")
    if not sample_dir:
        raise RuntimeError("sample.upload_h5 requires sampleDir")
    h5_files = input_json.get("h5Files")
    if isinstance(h5_files, str):
        h5_files = [h5_files]
    result = upload_h5_files(
        sample_dir=str(sample_dir),
        h5_destination=dest,
        h5_files=h5_files,
    )
    result["sampleId"] = input_json.get("sampleId") or Path(str(sample_dir)).name
    return result
