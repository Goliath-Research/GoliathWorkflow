"""Provision reference assets onto /work using recipe JSON."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    Step ops: ``download`` (uri or storage_endpoint_id + key), ``checksum``, ``run``, ``mkdir``.
    """
    work_root = Path(work_root)
    rec = store.get("reference_asset", asset_name, version=version, published_only=False)
    if rec is None:
        raise KeyError(f"reference_asset not found: {asset_name}")
    doc = rec.document
    recipe = doc.get("recipe") or {}
    steps: List[Dict[str, Any]] = list(recipe.get("steps") or [])
    dest_root = Path(doc.get("destRoot") or (work_root / "genomes" / asset_name))
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
                # Expand endpoint for logging; actual cloud download may use worker helpers later.
                loc = expand_storage_endpoint(
                    store, step["storageEndpoint"], prefix=step.get("prefix")
                )
                log.append(
                    f"download via endpoint {step['storageEndpoint']} "
                    f"({loc.get('type')}) key={step.get('key')} -> {dest}"
                )
                if not dry_run and loc.get("type") == "file":
                    src = Path(loc["basePath"]) / (step.get("key") or "")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                elif not dry_run and loc.get("type") == "https":
                    base = loc.get("baseUrl") or loc.get("url")
                    _download_https(f"{base.rstrip('/')}/{step.get('key', '')}", dest)
                elif not dry_run:
                    raise NotImplementedError(
                        f"provision download for provider {loc.get('type')} "
                        "requires worker cloud helpers; use dry_run or file/https"
                    )
            else:
                raise ValueError(f"download step {i} needs uri or storageEndpoint")
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
