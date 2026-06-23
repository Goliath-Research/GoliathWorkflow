"""Upload sample artifacts (FASTQs, QC JSON, HDF5) to durable sample storage."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from methyl_domain.sample_storage import (
    AzureSampleDestination,
    FileSampleDestination,
    SampleDestinationLocation,
    S3SampleDestination,
    resolve_file_local_root,
)

logger = logging.getLogger(__name__)

H5_SUFFIX = ".h5"
FASTQ_GLOBS = ("*.fastq.gz", "*.fq.gz", "*.fastq", "*.fq")
RAW_METRICS_SUFFIXES = (".pb_metrics.json",)


@dataclass(frozen=True)
class UploadTarget:
    scheme: str
    bucket: str = ""
    container: str = ""
    account: str = ""
    prefix: str = ""
    local_root: Path | None = None
    s3_dest: S3SampleDestination | None = None
    azure_dest: AzureSampleDestination | None = None


@dataclass
class _CloudClients:
    s3: Any = field(default=None, repr=False)
    azure: Any = field(default=None, repr=False)


def _remote_key(prefix: str, relative_path: str) -> str:
    norm = prefix.rstrip("/")
    rel = relative_path.lstrip("/")
    if not norm:
        return rel
    return f"{norm}/{rel}"


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
    if int(head["ContentLength"]) != local.stat().st_size:
        return False
    etag = str(head.get("ETag", "")).strip('"')
    return len(etag) == 32 and etag == _file_md5(local)


def _should_skip_azure(blob_client: Any, local: Path) -> bool:
    try:
        props = blob_client.get_blob_properties()
    except Exception:
        return False
    return int(props.size) == local.stat().st_size


def _s3_client(dest: S3SampleDestination):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for s3 sampleDestination") from exc

    from methyl_domain.fastq_storage import S3ExplicitKeysCredentials

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


def _azure_service(dest: AzureSampleDestination):
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError("azure-storage-blob required for azure_blob sampleDestination") from exc

    creds = dest.credentials
    if creds.authMode == "connection_string":
        return BlobServiceClient.from_connection_string(creds.connectionString.get_secret_value())
    if creds.authMode == "account_key":
        account_url = f"https://{dest.account}.blob.core.windows.net"
        return BlobServiceClient(account_url, credential=creds.accountKey.get_secret_value())
    account_url = f"https://{dest.account}.blob.core.windows.net"
    return BlobServiceClient(account_url, credential=DefaultAzureCredential())


def _target_from_model(dest: SampleDestinationLocation) -> UploadTarget:
    if isinstance(dest, FileSampleDestination):
        return UploadTarget(
            scheme="file",
            prefix=dest.prefix,
            local_root=resolve_file_local_root(dest),
        )
    if isinstance(dest, S3SampleDestination):
        return UploadTarget(
            scheme="s3",
            bucket=dest.bucket,
            prefix=dest.prefix,
            s3_dest=dest,
        )
    if isinstance(dest, AzureSampleDestination):
        return UploadTarget(
            scheme="az",
            account=dest.account,
            container=dest.container,
            prefix=dest.prefix,
            azure_dest=dest,
        )
    raise RuntimeError(f"Unsupported sample destination: {type(dest)!r}")


def _upload_one(
    local: Path,
    relative_path: str,
    target: UploadTarget,
    clients: _CloudClients,
) -> bool:
    """Upload file; return True if uploaded, False if skipped unchanged."""
    key = _remote_key(target.prefix, relative_path)
    if target.scheme == "file":
        root = target.local_root
        if root is None:
            raise RuntimeError("file sampleDestination missing local_root")
        dest_path = root / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.is_file() and dest_path.stat().st_size == local.stat().st_size:
            return False
        shutil.copy2(local, dest_path)
        return True

    if target.scheme == "s3":
        if clients.s3 is None:
            assert target.s3_dest is not None
            clients.s3 = _s3_client(target.s3_dest)
        if _should_skip_s3(clients.s3, target.bucket, key, local):
            logger.info("Skipping unchanged s3://%s/%s", target.bucket, key)
            return False
        clients.s3.upload_file(str(local), target.bucket, key)
        return True

    if target.scheme == "az":
        assert target.azure_dest is not None
        if clients.azure is None:
            clients.azure = _azure_service(target.azure_dest)
        blob_client = clients.azure.get_blob_client(container=target.container, blob=key)
        if _should_skip_azure(blob_client, local):
            logger.info("Skipping unchanged %s/%s", target.container, key)
            return False
        with open(local, "rb") as handle:
            blob_client.upload_blob(handle, overwrite=True)
        return True

    raise RuntimeError(f"Unsupported destination scheme {target.scheme!r}")


def _collect_fastqs(sample_dir: Path) -> List[Path]:
    paths: List[Path] = []
    for pattern in FASTQ_GLOBS:
        paths.extend(sorted(sample_dir.glob(pattern)))
    trimmed = [p for p in paths if ".trimmed." in p.name]
    if trimmed:
        return trimmed
    return paths


def _resolve_alignment_qc_path(
    sample_dir: Path,
    sample_id: str,
    alignment_qc_path: Optional[str | Path],
    project_path: Optional[str | Path],
) -> Optional[Path]:
    if alignment_qc_path:
        path = Path(str(alignment_qc_path))
        if path.is_file():
            return path
    candidate = sample_dir / f"{sample_id}.json"
    if candidate.is_file():
        return candidate
    if project_path:
        try:
            from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config

            cfg = resolve_alignment_qc_config(str(project_path))
            out = Path(cfg.output_dir) / f"{sample_id}.json"
            if out.is_file():
                return out
        except Exception:
            logger.debug("Could not resolve alignment QC from project", exc_info=True)
    return None


def _artifact_entries(
    *,
    sample_dir: Path,
    sample_id: str,
    mode: str,
    alignment_qc_path: Optional[str | Path],
    project_path: Optional[str | Path],
) -> List[Tuple[Path, str]]:
    """Return (local_path, archive_relative_path) pairs."""
    entries: List[Tuple[Path, str]] = []

    align = _resolve_alignment_qc_path(sample_dir, sample_id, alignment_qc_path, project_path)
    if align is not None:
        entries.append((align, "qc/alignment.json"))

    extraction_qc = sample_dir / f"{sample_id}.extraction_qc.json"
    if extraction_qc.is_file():
        entries.append((extraction_qc, "qc/extraction_qc.json"))

    manifest = sample_dir / f"{sample_id}.extraction_manifest.json"
    if manifest.is_file() and mode == "full":
        entries.append((manifest, "qc/extraction_manifest.json"))

    log_path = sample_dir / f"{sample_id}.sample_prep_log.jsonl"
    if log_path.is_file():
        entries.append((log_path, "qc/sample_prep_log.jsonl"))

    if mode == "full":
        for fq in _collect_fastqs(sample_dir):
            entries.append((fq, f"fastq/{fq.name}"))
        for h5 in sorted(sample_dir.glob(f"*{H5_SUFFIX}")):
            entries.append((h5, f"h5/{h5.name}"))

    return entries


def archive_sample(
    *,
    sample_dir: str | Path,
    sample_id: str,
    sample_destination: SampleDestinationLocation,
    mode: str = "full",
    reject_reason: Optional[str] = None,
    alignment_qc_path: Optional[str | Path] = None,
    project_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    if mode not in {"full", "qc_only"}:
        raise RuntimeError(f"archive mode must be 'full' or 'qc_only', got {mode!r}")
    if mode == "qc_only" and not reject_reason:
        reject_reason = "qc_failed"

    sample_path = Path(sample_dir)
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    target = _target_from_model(sample_destination)
    clients = _CloudClients()
    uploaded: List[str] = []
    skipped: List[str] = []
    manifest_files: List[dict[str, Any]] = []

    for local, rel in _artifact_entries(
        sample_dir=sample_path,
        sample_id=sample_id,
        mode=mode,
        alignment_qc_path=alignment_qc_path,
        project_path=project_path,
    ):
        if not local.is_file():
            continue
        if local.suffix == ".json" and any(local.name.endswith(s) for s in RAW_METRICS_SUFFIXES):
            continue
        did_upload = _upload_one(local, rel, target, clients)
        entry = {
            "path": rel,
            "size": local.stat().st_size,
            "md5": _file_md5(local),
        }
        manifest_files.append(entry)
        if did_upload:
            uploaded.append(rel)
        else:
            skipped.append(rel)

    archive_manifest = {
        "schema_name": "methylpipeline.sample_archive",
        "schema_version": "1.0.0",
        "sample_id": sample_id,
        "archive_mode": mode,
        "reject_reason": reject_reason if mode == "qc_only" else None,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "remote_prefix": target.prefix,
        "files": manifest_files,
    }

    manifest_local = sample_path / "archive_manifest.json"
    manifest_local.write_text(json.dumps(archive_manifest, indent=2), encoding="utf-8")
    _upload_one(manifest_local, "archive_manifest.json", target, clients)
    uploaded.append("archive_manifest.json")

    return {
        "sampleId": sample_id,
        "archiveMode": mode,
        "rejectReason": reject_reason,
        "uploadedFiles": uploaded,
        "skippedFiles": skipped,
        "remotePrefix": target.prefix,
        "uploadedCount": len(uploaded),
        "skippedCount": len(skipped),
        "sampleArchived": True,
        "archiveManifestPath": str(manifest_local),
    }


def _resolve_destination(input_json: Mapping[str, Any]) -> SampleDestinationLocation:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(SampleDestinationLocation)
    raw = input_json.get("sampleDestination") or input_json.get("h5Destination")
    if raw is None:
        raise RuntimeError("sample.archive_sample requires sampleDestination")
    return adapter.validate_python(raw)


def archive_from_task_input(input_json: Mapping[str, Any]) -> dict[str, Any]:
    sample_dir = input_json.get("sampleDir")
    if not sample_dir:
        raise RuntimeError("sample.archive_sample requires sampleDir")
    sample_id = str(input_json.get("sampleId") or Path(str(sample_dir)).name)
    mode = str(input_json.get("mode") or input_json.get("archiveMode") or "full")
    return archive_sample(
        sample_dir=str(sample_dir),
        sample_id=sample_id,
        sample_destination=_resolve_destination(input_json),
        mode=mode,
        reject_reason=input_json.get("rejectReason"),
        alignment_qc_path=input_json.get("alignmentQcPath") or input_json.get("qcPath"),
        project_path=input_json.get("projectPath") or input_json.get("project"),
    )


# Backward-compatible H5-only upload (flat keys under prefix; does not archive FASTQs/QC).
def _local_h5_files(sample_dir: Path, h5_files: Sequence[str] | None) -> List[Path]:
    if h5_files:
        paths = [sample_dir / name for name in h5_files]
    else:
        paths = sorted(sample_dir.glob(f"*{H5_SUFFIX}"))
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise RuntimeError(f"HDF5 files not found: {', '.join(str(p) for p in missing)}")
    return paths


def upload_h5_files(
    *,
    sample_dir: str | Path,
    h5_destination: SampleDestinationLocation,
    h5_files: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Upload only HDF5 files to the destination prefix (legacy flat layout)."""
    sample_path = Path(sample_dir)
    local_files = _local_h5_files(sample_path, h5_files)
    target = _target_from_model(h5_destination)
    clients = _CloudClients()
    uploaded: List[str] = []
    skipped: List[str] = []

    for local in local_files:
        rel = local.name
        if _upload_one(local, rel, target, clients):
            uploaded.append(rel)
        else:
            skipped.append(rel)

    return {
        "uploadedFiles": uploaded,
        "skippedFiles": skipped,
        "remotePrefix": target.prefix,
        "uploadedCount": len(uploaded),
        "skippedCount": len(skipped),
    }


def upload_h5_from_task_input(input_json: Mapping[str, Any]) -> dict[str, Any]:
    sample_dir = input_json.get("sampleDir")
    if not sample_dir:
        raise RuntimeError("sample.upload_h5 requires sampleDir")
    h5_files = input_json.get("h5Files")
    if isinstance(h5_files, str):
        h5_files = [h5_files]
    result = upload_h5_files(
        sample_dir=str(sample_dir),
        h5_destination=_resolve_destination(input_json),
        h5_files=h5_files,
    )
    result["sampleId"] = input_json.get("sampleId") or Path(str(sample_dir)).name
    return result


def upload_from_task_input(input_json: Mapping[str, Any]) -> dict[str, Any]:
    """Deprecated alias — use ``upload_h5_from_task_input`` for H5-only uploads."""
    return upload_h5_from_task_input(input_json)
