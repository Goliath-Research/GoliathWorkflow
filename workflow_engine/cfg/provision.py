"""Provision reference assets onto /work using recipe JSON."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .reference_selection import apply_reference_selection, selected_asset_names
from .store import ConfigStore
from .storage_expand import expand_storage_endpoint


def _checksum_file(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_https(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def _aws_s3_env(loc: Dict[str, Any]) -> Dict[str, str]:
    """Build env for aws CLI from expanded storage location."""
    env = os.environ.copy()
    region = str(loc.get("region") or env.get("AWS_DEFAULT_REGION") or "us-east-1")
    env["AWS_DEFAULT_REGION"] = region
    creds = loc.get("credentials") or {}
    access = creds.get("accessKeyId") or creds.get("access_key_id")
    secret = creds.get("secretAccessKey") or creds.get("secret_access_key")
    if access and secret:
        env["AWS_ACCESS_KEY_ID"] = str(access)
        env["AWS_SECRET_ACCESS_KEY"] = str(secret)
    token = creds.get("sessionToken") or creds.get("session_token")
    if token:
        env["AWS_SESSION_TOKEN"] = str(token)
    return env


def _run_aws_s3(
    argv: List[str],
    *,
    loc: Dict[str, Any],
    dry_run: bool,
) -> None:
    if not shutil.which("aws"):
        raise RuntimeError("aws CLI is required for S3 provision downloads")
    endpoint = loc.get("endpointUrl") or loc.get("endpoint_url")
    region = str(loc.get("region") or "us-east-1")
    cmd = ["aws", *argv, "--region", region]
    if endpoint:
        cmd.extend(["--endpoint-url", str(endpoint)])
    if dry_run and "sync" in argv:
        cmd.append("--dryrun")

    conf_dir = tempfile.mkdtemp(prefix="aws-provision-")
    try:
        conf = Path(conf_dir) / "config"
        conf.write_text(
            f"[default]\nregion = {region}\ns3 =\n    addressing_style = path\n",
            encoding="utf-8",
        )
        empty_creds = Path(conf_dir) / "empty_credentials"
        empty_creds.write_text("", encoding="utf-8")
        env = _aws_s3_env(loc)
        env["AWS_CONFIG_FILE"] = str(conf)
        env["AWS_SHARED_CREDENTIALS_FILE"] = str(empty_creds)
        if not (env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY")):
            auth = (loc.get("credentials") or {}).get("authMode")
            if auth not in ("instance_profile", "default_credential", "application_default"):
                raise RuntimeError(
                    "S3 provision requires accessKeyId/secretAccessKey on the "
                    "storage endpoint credential (or instance_profile authMode)"
                )
        subprocess.run(cmd, check=True, env=env)
    finally:
        shutil.rmtree(conf_dir, ignore_errors=True)


def _s3_uri(loc: Dict[str, Any], key: str = "") -> str:
    bucket = loc.get("bucket")
    if not bucket:
        raise ValueError("S3 storage endpoint missing bucket")
    prefix_base = (loc.get("prefixBase") or loc.get("prefix") or "").strip("/")
    key = (key or "").lstrip("/")
    parts = [p for p in (prefix_base, key) if p]
    path = "/".join(parts)
    if path and not path.endswith("/") and key.endswith("/"):
        path += "/"
    return f"s3://{bucket}/{path}" if path else f"s3://{bucket}/"


def _download_s3_object(loc: Dict[str, Any], key: str, dest: Path, *, dry_run: bool) -> None:
    uri = _s3_uri(loc, key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return
    _run_aws_s3(["s3", "cp", uri, str(dest)], loc=loc, dry_run=False)


def _sync_s3_prefix(loc: Dict[str, Any], prefix: str, dest: Path, *, dry_run: bool) -> None:
    # Ensure trailing slash for directory sync semantics
    key = prefix if prefix.endswith("/") else f"{prefix}/"
    uri = _s3_uri(loc, key)
    if dry_run:
        # Do not contact the endpoint during dry-run (log-only).
        return
    dest.mkdir(parents=True, exist_ok=True)
    _run_aws_s3(
        ["s3", "sync", uri, str(dest) + "/"],
        loc=loc,
        dry_run=False,
    )


def provision_asset(
    store: ConfigStore,
    asset_name: str,
    *,
    work_root: Path | str,
    version: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute ``document.recipe.steps`` for a reference_asset.

    Step ops: ``mkdir``, ``download`` (uri / file / https / s3), ``s3_sync``,
    ``checksum``, ``run``.
    """
    work_root = Path(work_root)
    rec = store.get("reference_asset", asset_name, version=version, published_only=False)
    if rec is None:
        raise KeyError(f"reference_asset not found: {asset_name}")
    doc = rec.document
    recipe = doc.get("recipe") or {}
    steps: List[Dict[str, Any]] = list(recipe.get("steps") or [])
    dest_root = Path(doc.get("destRoot") or (work_root / "genomes" / asset_name))
    if not dest_root.is_absolute():
        dest_root = work_root / dest_root
    log: List[str] = []

    for i, step in enumerate(steps):
        op = step.get("op")
        if op == "mkdir":
            path = Path(step.get("path") or dest_root)
            if not path.is_absolute():
                path = work_root / path
            log.append(f"mkdir {path}")
            if not dry_run:
                path.mkdir(parents=True, exist_ok=True)
        elif op == "download":
            dest = Path(step["dest"])
            if not dest.is_absolute():
                dest = dest_root / dest if dest_root else work_root / dest
            uri = step.get("uri")
            if uri:
                log.append(f"download {uri} -> {dest}")
                if not dry_run:
                    _download_https(uri, dest)
            elif step.get("storageEndpoint"):
                loc = expand_storage_endpoint(
                    store, step["storageEndpoint"], prefix=step.get("prefix")
                )
                key = step.get("key") or ""
                log.append(
                    f"download via endpoint {step['storageEndpoint']} "
                    f"({loc.get('type')}) key={key} -> {dest}"
                )
                if dry_run:
                    continue
                if loc.get("type") == "file":
                    src = Path(loc["basePath"]) / key
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                elif loc.get("type") == "https":
                    base = loc.get("baseUrl") or loc.get("url")
                    _download_https(f"{base.rstrip('/')}/{key}", dest)
                elif loc.get("type") == "s3":
                    _download_s3_object(loc, key, dest, dry_run=False)
                else:
                    raise NotImplementedError(
                        f"provision download for provider {loc.get('type')} "
                        "requires worker cloud helpers; use dry_run or file/https/s3"
                    )
            else:
                raise ValueError(f"download step {i} needs uri or storageEndpoint")
        elif op == "s3_sync":
            if not step.get("storageEndpoint"):
                raise ValueError(f"s3_sync step {i} needs storageEndpoint")
            # The step key/prefix is the sync key relative to the endpoint's own
            # base (prefixBase); do not also bake it onto loc["prefix"], or
            # _s3_uri would double-apply it for endpoints without prefixBase.
            loc = expand_storage_endpoint(store, step["storageEndpoint"])
            if loc.get("type") != "s3":
                raise ValueError(
                    f"s3_sync step {i} requires s3 endpoint, got {loc.get('type')}"
                )
            prefix = step.get("key") or step.get("prefix") or ""
            dest = Path(step.get("dest") or dest_root)
            if not dest.is_absolute():
                dest = dest_root / dest if step.get("dest") else dest_root
            log.append(
                f"s3_sync endpoint={step['storageEndpoint']} prefix={prefix} -> {dest}"
            )
            _sync_s3_prefix(loc, prefix, dest, dry_run=dry_run)
        elif op == "checksum":
            path = Path(step["path"])
            if not path.is_absolute():
                path = dest_root / path
            expect = step.get("sha256") or step.get("md5")
            algo = "sha256" if step.get("sha256") else "md5"
            log.append(f"checksum {algo} {path}")
            if not dry_run:
                got = _checksum_file(path, algo)
                if expect and got.lower() != str(expect).lower():
                    raise RuntimeError(f"checksum mismatch for {path}: {got} != {expect}")
        elif op == "run":
            argv = list(step.get("argv") or [])
            cwd = step.get("cwd")
            cwd_path = Path(cwd) if cwd else dest_root
            if not cwd_path.is_absolute():
                cwd_path = work_root / cwd_path
            log.append(f"run {argv} cwd={cwd_path}")
            if not dry_run:
                subprocess.run(argv, cwd=str(cwd_path), check=True)
        else:
            raise ValueError(f"unknown recipe op: {op}")

    return {
        "asset": asset_name,
        "version": rec.version,
        "destRoot": str(dest_root),
        "dryRun": dry_run,
        "log": log,
    }


def provision_all_published(
    store: ConfigStore, work_root: Path | str, *, dry_run: bool = False
) -> Dict[str, Any]:
    results = []
    for rec in store.list("reference_asset", published_only=True):
        results.append(
            provision_asset(store, rec.name, work_root=work_root, version=rec.version, dry_run=dry_run)
        )
    return {"results": results}


def provision_selected_from_site(
    store: ConfigStore,
    *,
    work_root: Path | str,
    site_name: str = "default",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Provision only reference_assets named by the site's ``reference_selection``."""
    site = store.get("site", site_name, published_only=False)
    if site is None:
        raise KeyError(f"site not found: {site_name}")
    names = selected_asset_names(site.document)
    if not names:
        raise ValueError(
            f"site {site_name} has no reference_selection pins mapping to assets"
        )
    results = []
    for _sel_key, asset_name in names.items():
        results.append(
            provision_asset(store, asset_name, work_root=work_root, dry_run=dry_run)
        )
    return {
        "site": site_name,
        "selection": site.document.get("reference_selection") or {},
        "results": results,
    }


def materialize_site_with_selection(
    store: ConfigStore,
    *,
    work_root: Path | str,
    site_name: str = "default",
) -> Dict[str, Any]:
    """Write ``/work/site/methyl_site.json`` with paths filled from reference_selection."""
    work_root = Path(work_root)
    site = store.get("site", site_name, published_only=True) or store.get(
        "site", site_name, published_only=False
    )
    if site is None:
        raise KeyError(f"site not found: {site_name}")
    doc = apply_reference_selection(site.document, work_root=work_root, overwrite=False)
    out = work_root / "site" / "methyl_site.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    import json

    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"site": site_name, "path": str(out), "reference_selection": doc.get("reference_selection")}
