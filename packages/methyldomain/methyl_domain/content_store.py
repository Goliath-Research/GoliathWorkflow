"""Content-addressed action store (CAAS) for hyperparameter-versioned results."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Set, Type, TypeVar

from pydantic import BaseModel

from .action_result import (
    ActionExecutionRecord,
    ArtifactRef,
    atomic_write_action_result,
    caas_entry_dir,
    caas_entry_manifest_path,
    instance_ledger_path,
    read_action_result,
    utc_now,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_ACTION_RESULTS_DIRNAME = ".action_results"


def compute_artifacts_signature(artifacts: Sequence[ArtifactRef]) -> str:
    """Hash artifact metadata (path, size, mtime) for idempotency checks."""
    if not artifacts:
        return hashlib.sha256(b"").hexdigest()
    parts: List[str] = []
    for ref in sorted(artifacts, key=lambda r: r.path):
        fp = f"{ref.path}:{ref.bytes or 0}"
        if ref.sha256:
            fp += f":{ref.sha256}"
        else:
            try:
                st = Path(ref.path).stat()
                fp += f":{int(st.st_mtime)}"
            except OSError:
                fp += ":missing"
        parts.append(fp)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def caas_enabled(input_json: Mapping[str, Any]) -> bool:
    """Return True when CAAS commit/reuse is active for this task.

    CAAS is **on by default** for every project/run. Operators may opt out with
    task ``caasEnabled: false`` or ``METHYL_CAAS_ENABLED=0`` (false/no/off).
    Explicit ``caasEnabled: true`` / env truthy values still force enable.
    """
    if input_json.get("caasEnabled") is True:
        return True
    if input_json.get("caasEnabled") is False:
        return False
    env = os.environ.get("METHYL_CAAS_ENABLED", "").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return False
    if env in {"1", "true", "yes", "on"}:
        return True
    return True


def resolve_project_root(input_json: Mapping[str, Any]) -> Optional[Path]:
    """Resolve ``{output_base}/{project_name}`` from task inputs."""
    explicit = input_json.get("projectRoot")
    if explicit:
        return Path(str(explicit)).expanduser().resolve()

    mc_root = input_json.get("monteCarloRunsRoot")
    if mc_root:
        return Path(str(mc_root)).expanduser().resolve().parent

    run_dir = input_json.get("runDir")
    if run_dir:
        p = Path(str(run_dir)).expanduser().resolve()
        parts = p.parts
        if "monte_carlo_runs" in parts:
            idx = parts.index("monte_carlo_runs")
            return Path(*parts[:idx])
        if p.name.startswith("run_") and p.parent.name == "monte_carlo_runs":
            return p.parent.parent

    project = input_json.get("projectPath") or input_json.get("project")
    if not project:
        return None
    path = Path(str(project)).expanduser().resolve()
    if path.is_file():
        try:
            from methyl_utils import load_project

            cfg = load_project(str(path))
            return Path(cfg.output_base) / cfg.project_name
        except Exception:
            return path.parent
    return path


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _product_artifact_paths(artifacts: Sequence[ArtifactRef]) -> List[Path]:
    paths: List[Path] = []
    for ref in artifacts:
        p = Path(ref.path)
        if _ACTION_RESULTS_DIRNAME in p.parts:
            continue
        paths.append(p)
    return paths


def _should_commit_directory(output_dir: Path, artifacts: Sequence[ArtifactRef]) -> bool:
    product_paths = _product_artifact_paths(artifacts)
    if product_paths and output_dir.is_dir():
        for path in product_paths:
            if not _is_under(path, output_dir):
                return False
        return True
    if not output_dir.is_dir():
        return False
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if _ACTION_RESULTS_DIRNAME in path.parts:
            continue
        return True
    return False


def _relative_under(root: Path, path: Path) -> Path:
    return path.resolve().relative_to(root.resolve())


def _symlink_target_for(link_path: Path, target: Path) -> Path | str:
    """Prefer a project-local relative symlink target.

    Absolute ``resolve()`` targets break when the same NFS volume is visible as both
    ``/work/...`` and ``/lambda/nfs/Work/...`` (or when bind-mount prefixes differ).
    Relative targets stay valid as long as link and blob share one filesystem tree.
    """
    target_resolved = target.expanduser().resolve()
    link_parent = link_path.expanduser().parent
    try:
        link_parent_resolved = link_parent.resolve()
    except OSError:
        link_parent.mkdir(parents=True, exist_ok=True)
        link_parent_resolved = link_parent.resolve()
    try:
        return os.path.relpath(target_resolved, start=link_parent_resolved)
    except ValueError:
        return target_resolved


def _ensure_symlink(link_path: Path, target: Path) -> None:
    link_path = link_path.expanduser()
    target_resolved = target.expanduser().resolve()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink():
        try:
            if link_path.resolve() == target_resolved:
                return
        except OSError:
            pass
        link_path.unlink()
    elif link_path.exists():
        if link_path.is_dir():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()
    link_path.symlink_to(_symlink_target_for(link_path, target_resolved))


def _move_tree_into_entry(
    source_root: Path,
    entry_dir: Path,
    *,
    exclude_names: Optional[Set[str]] = None,
) -> List[Path]:
    """Move files from source_root into entry_dir, preserving relative layout."""
    exclude = exclude_names or set()
    moved: List[Path] = []
    source_root = source_root.resolve()
    entry_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source_root)
        if any(part in exclude for part in rel.parts):
            continue
        dest = entry_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        shutil.move(str(path), str(dest))
        moved.append(dest)
    return moved


def _move_artifacts_into_entry(
    artifacts: Sequence[ArtifactRef],
    entry_dir: Path,
) -> List[ArtifactRef]:
    """Move product artifact files into entry_dir (flat basename layout)."""
    entry_dir.mkdir(parents=True, exist_ok=True)
    updated: List[ArtifactRef] = []
    for ref in artifacts:
        src = Path(ref.path)
        if not src.is_file() or _ACTION_RESULTS_DIRNAME in src.parts:
            continue
        dest = entry_dir / src.name
        if dest.exists() and dest.resolve() != src.resolve():
            dest.unlink()
        if src.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), str(dest))
        updated.append(
            ArtifactRef(
                path=str(dest.resolve()),
                kind=ref.kind,
                bytes=dest.stat().st_size if dest.is_file() else ref.bytes,
                sha256=ref.sha256,
            )
        )
    return updated


def _relink_artifacts_from_entry(
    artifacts: Sequence[ArtifactRef],
    entry_dir: Path,
    *,
    output_dir: Optional[Path] = None,
) -> List[ArtifactRef]:
    """Create symlinks at canonical artifact paths pointing into entry_dir."""
    entry_dir = entry_dir.resolve()
    relinked: List[ArtifactRef] = []
    for ref in artifacts:
        stored = Path(ref.path)
        if not stored.is_file():
            if stored.is_symlink():
                stored = stored.resolve()
            if not stored.is_file():
                continue
        try:
            rel = stored.relative_to(entry_dir)
        except ValueError:
            rel = Path(stored.name)
        if output_dir is not None:
            canonical = output_dir / rel
        else:
            canonical = Path(ref.path)
        _ensure_symlink(canonical, stored)
        relinked.append(
            ArtifactRef(
                path=str(canonical.resolve()),
                kind=ref.kind,
                bytes=stored.stat().st_size,
                sha256=ref.sha256,
            )
        )
    return relinked


def verify_entry_artifacts(record: ActionExecutionRecord) -> bool:
    """Return True when every product artifact in a CAAS manifest exists on disk."""
    product_paths = _product_artifact_paths(record.artifacts)
    if not product_paths:
        return False
    for path in product_paths:
        if path.is_symlink():
            path = path.resolve()
        if not path.is_file():
            return False
        for ref in record.artifacts:
            if Path(ref.path).resolve() == path or Path(ref.path) == path:
                if ref.bytes is not None:
                    try:
                        if path.stat().st_size != ref.bytes:
                            return False
                    except OSError:
                        return False
                break
    return True


def read_caas_entry(
    project_root: Path | str,
    action_name: str,
    content_key: str,
    *,
    model: Type[T] = ActionExecutionRecord,
) -> Optional[T]:
    manifest_path = caas_entry_manifest_path(project_root, action_name, content_key)
    if not manifest_path.is_file():
        return None
    try:
        return read_action_result(manifest_path, model)
    except Exception:
        logger.debug("could not read CAAS manifest %s", manifest_path, exc_info=True)
        return None


def link_entry_into_place(
    project_root: Path | str,
    action_name: str,
    content_key: str,
    *,
    output_dir: Optional[Path | str] = None,
) -> Optional[ActionExecutionRecord]:
    """Relink canonical artifact paths to an existing CAAS entry."""
    record = read_caas_entry(project_root, action_name, content_key)
    if record is None or record.result_code != 0:
        return None
    if not verify_entry_artifacts(record):
        return None

    entry_dir = caas_entry_dir(project_root, action_name, content_key)
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else None
    relinked = _relink_artifacts_from_entry(record.artifacts, entry_dir, output_dir=out_dir)
    if not relinked:
        return None
    updated = record.model_copy(update={"artifacts": relinked})
    return updated


def commit_artifacts_to_store(
    project_root: Path | str,
    action_name: str,
    content_key: str,
    record: ActionExecutionRecord,
    *,
    output_dir: Optional[Path | str] = None,
) -> ActionExecutionRecord:
    """
    Move product artifacts into CAAS and relink canonical paths as symlinks.

    If another worker already committed the same content_key, reuse that entry.
    """
    project_root = Path(project_root)
    entry_dir = caas_entry_dir(project_root, action_name, content_key)
    manifest_path = caas_entry_manifest_path(project_root, action_name, content_key)

    existing = read_caas_entry(project_root, action_name, content_key)
    if existing is not None and verify_entry_artifacts(existing):
        out_dir = Path(output_dir).expanduser().resolve() if output_dir else None
        relinked = _relink_artifacts_from_entry(existing.artifacts, entry_dir, output_dir=out_dir)
        return existing.model_copy(
            update={
                "artifacts": relinked or existing.artifacts,
                "content_key": content_key,
                "hyperparam_set_id": record.hyperparam_set_id or existing.hyperparam_set_id,
            }
        )

    entry_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else None
    product_paths = _product_artifact_paths(record.artifacts)

    if out_dir is not None and _should_commit_directory(out_dir, record.artifacts):
        moved = _move_tree_into_entry(
            out_dir,
            entry_dir,
            exclude_names={_ACTION_RESULTS_DIRNAME},
        )
        stored_artifacts = [
            ArtifactRef(
                path=str(p.resolve()),
                kind="file",
                bytes=p.stat().st_size,
            )
            for p in moved
        ]
        if out_dir.exists() and not any(out_dir.iterdir()):
            # Keep output_dir as a mount point; relink each stored file beneath it.
            pass
        relinked = _relink_artifacts_from_entry(stored_artifacts, entry_dir, output_dir=out_dir)
    else:
        stored_artifacts = _move_artifacts_into_entry(record.artifacts, entry_dir)
        relinked = _relink_artifacts_from_entry(
            stored_artifacts,
            entry_dir,
            output_dir=out_dir,
        )

    if not relinked and product_paths:
        relinked = list(record.artifacts)

    output_signature = compute_artifacts_signature(relinked or record.artifacts)

    committed = record.model_copy(
        update={
            "schema_version": "1.2",
            "content_key": content_key,
            "artifacts": relinked or record.artifacts,
            "output_signature": output_signature,
            "manifest_path": str(manifest_path),
        }
    )
    atomic_write_action_result(manifest_path, committed)
    return committed


def append_instance_ledger(
    project_root: Path | str,
    hyperparam_set_id: str,
    *,
    action_name: str,
    run_key: str,
    content_key: str,
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Record action+run_key -> content_key for one hyperparameter set."""
    if not hyperparam_set_id:
        return
    from .action_result import atomic_write_json

    ledger_path = instance_ledger_path(project_root, hyperparam_set_id)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any]
    if ledger_path.is_file():
        import json

        with open(ledger_path, encoding="utf-8") as fh:
            payload = json.load(fh)
    else:
        payload = {
            "hyperparam_set_id": hyperparam_set_id,
            "entries": {},
        }

    key = f"{action_name}:{run_key}"
    entry: dict[str, Any] = {
        "action_name": action_name,
        "run_key": run_key,
        "content_key": content_key,
        "recorded_at_utc": utc_now().isoformat(),
    }
    if extra:
        entry.update(dict(extra))
    entries = payload.setdefault("entries", {})
    if isinstance(entries, dict):
        entries[key] = entry
    atomic_write_json(ledger_path, payload)
