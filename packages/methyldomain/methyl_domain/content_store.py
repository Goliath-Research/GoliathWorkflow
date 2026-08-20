"""Content-addressed action store (CAAS) for hyperparameter-versioned results."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
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


def resolve_caas_root(
    input_json: Mapping[str, Any],
    *,
    action_name: Optional[str] = None,
) -> Optional[Path]:
    """Resolve CAAS store root: sample-scoped when enabled, else study project root."""
    if action_name:
        from .sample_content_store import (
            resolve_sample_caas_root,
            sample_caas_enabled_for_action,
        )

        if sample_caas_enabled_for_action(action_name, input_json):
            sample_root = resolve_sample_caas_root(input_json)
            if sample_root is not None:
                return sample_root
    return resolve_project_root(input_json)


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


def _is_durable_caas_blob(path: Path) -> bool:
    """True when ``path`` is a real file stored under a ``.caas/`` content-key.

    Product paths (``sampleDir/S1.bam``, ``output_dir/summary.json``) are never
    this. ``artifact_ref_for`` records ``Path.resolve()``, so a later commit may
    see the blob path instead of the product symlink. Rewriting that file as a
    symlink into a new entry destroys skip-replay for the prior key.
    """
    try:
        if path.is_symlink() or not path.is_file():
            return False
    except OSError:
        return False
    return ".caas" in path.parts


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
    """Return True only when output_dir is exclusively owned by this action's artifacts.

    Shared product directories (e.g. multi-chromosome ``pipeline.centroid`` writing into the
    same ``.../centroids/.../all`` folder) must use flat per-artifact commits. Tree-moving
    the whole directory would steal sibling chromosome files/symlinks into the wrong
    content_key and leave broken product paths.
    """
    product_paths = _product_artifact_paths(artifacts)
    if not product_paths or not output_dir.is_dir():
        return False
    for path in product_paths:
        if not _is_under(path, output_dir):
            return False

    owned: Set[Path] = set()
    for path in product_paths:
        try:
            owned.add(path.expanduser().resolve())
        except OSError:
            owned.add(path.expanduser())

    for path in output_dir.rglob("*"):
        if _ACTION_RESULTS_DIRNAME in path.parts or ".caas" in path.parts:
            continue
        if not (path.is_file() or path.is_symlink()):
            continue
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            # Dangling sibling symlink from another content_key — shared dir.
            return False
        if resolved not in owned:
            return False
    return True


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
    """Create or replace ``link_path`` as a symlink to ``target``.

    Uses a temp link + ``os.replace`` so concurrent workers sharing an output
    directory (portal / local ``--parallel-workers``) do not race on
    ``FileExistsError`` between unlink and symlink.
    """
    link_path = link_path.expanduser()
    target_resolved = target.expanduser().resolve()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    desired = _symlink_target_for(link_path, target_resolved)
    if link_path.is_symlink():
        try:
            if link_path.resolve() == target_resolved:
                return
        except OSError:
            pass
    elif link_path.exists() and link_path.is_dir() and not link_path.is_symlink():
        shutil.rmtree(link_path)

    tmp = link_path.with_name(
        f".{link_path.name}.caas-link-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    )
    try:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        tmp.symlink_to(desired)
        os.replace(tmp, link_path)
    except OSError:
        if tmp.exists() or tmp.is_symlink():
            try:
                tmp.unlink()
            except OSError:
                pass
        # Another worker may have won the race with the same target.
        if link_path.is_symlink():
            try:
                if link_path.resolve() == target_resolved:
                    return
            except OSError:
                pass
        raise


def _move_tree_into_entry(
    source_root: Path,
    entry_dir: Path,
    *,
    exclude_names: Optional[Set[str]] = None,
) -> List[Path]:
    """Move files from source_root into entry_dir, preserving relative layout.

    Skips symlinks (including CAAS product links) so a tree commit cannot pull
    sibling content-addressed blobs into this entry.
    """
    exclude = exclude_names or set()
    moved: List[Path] = []
    source_root = source_root.resolve()
    entry_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_root.rglob("*")):
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(source_root)
        if any(part in exclude or part == ".caas" for part in rel.parts):
            continue
        dest = entry_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        shutil.move(str(path), str(dest))
        moved.append(dest)
    return moved


def _abspath_nofollow(path: Path) -> Path:
    """Absolute path without resolving a leaf symlink."""
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.abspath(path))


def _relative_to_root_nofollow(path: Path, root: Path) -> Optional[Path]:
    """Return ``path`` relative to ``root`` without following a leaf symlink."""
    path_abs = _abspath_nofollow(path)
    root_abs = _abspath_nofollow(root)
    try:
        return path_abs.relative_to(root_abs)
    except ValueError:
        return None


def _caas_run_relative(path: Path) -> Optional[Path]:
    """Recover ``run_####/...`` from a path under ``.caas/.../validation_plan_iterations/<key>/``."""
    parts = Path(path).parts
    try:
        marker = parts.index("validation_plan_iterations")
    except ValueError:
        return None
    if len(parts) <= marker + 2:
        return None
    return Path(*parts[marker + 2 :])


def _move_artifacts_into_entry(
    artifacts: Sequence[ArtifactRef],
    entry_dir: Path,
    *,
    output_dir: Optional[Path] = None,
) -> List[ArtifactRef]:
    """Move product artifact files into entry_dir.

    When ``output_dir`` is set and an artifact lives under it, preserve the
    relative path (required for ``validation.plan_iterations``, which emits many
    ``run_####/project.json`` files with the same basename). Flat basename storage
    would collapse those into a single CAAS blob and relink only at the MC root.

    Leaf CAAS product symlinks under ``output_dir`` must keep that relative layout
    and must be **copied** (not moved) so a re-commit under a new content_key cannot
    steal blobs from a sibling entry.

    Without a usable relative root, fall back to basename (safe when names are
    unique in a shared directory, e.g. per-chromosome centroid HDF5s).
    """
    entry_dir.mkdir(parents=True, exist_ok=True)
    out_root = output_dir.expanduser().resolve() if output_dir is not None else None
    updated: List[ArtifactRef] = []
    for ref in artifacts:
        src = Path(ref.path).expanduser()
        if _ACTION_RESULTS_DIRNAME in src.parts:
            continue
        if not (src.is_file() or src.is_symlink()):
            continue
        # Readable payload (follow leaf symlink only for content).
        try:
            src_payload = src.resolve() if src.is_symlink() else src.resolve()
        except OSError:
            continue
        if not src_payload.is_file():
            continue

        rel: Optional[Path] = None
        if out_root is not None:
            rel = _relative_to_root_nofollow(src, out_root)
        if rel is None:
            rel = _caas_run_relative(src_payload)
        if rel is None and out_root is not None and _is_under(src_payload, out_root):
            rel = src_payload.relative_to(out_root)
        dest = entry_dir / rel if rel is not None else entry_dir / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            same_path = dest.exists() and dest.resolve() == src_payload.resolve()
        except OSError:
            same_path = False
        if not same_path:
            if dest.exists() or dest.is_symlink():
                if dest.is_dir() and not dest.is_symlink():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            # Never move a blob out of another CAAS content-key entry.
            foreign_caas_blob = (
                ".caas" in src_payload.parts
                and not _is_under(src_payload, entry_dir)
            )
            if src.is_symlink() or foreign_caas_blob:
                shutil.copy2(str(src_payload), str(dest))
                # Remove only the logical product path (usually a symlink under
                # output_dir). Never delete the foreign CAAS blob we copied from.
                if src.is_symlink() or (
                    out_root is not None and _relative_to_root_nofollow(src, out_root) is not None
                ):
                    if src.exists() or src.is_symlink():
                        if not (src.is_dir() and not src.is_symlink()):
                            src.unlink()
            else:
                shutil.move(str(src_payload), str(dest))
        # Restore the canonical product path as a symlink into this entry.
        # Do not rewrite a durable blob under ``.caas/`` — harvest often records
        # resolve()d CAAS paths; replacing that file would break skip-replay of
        # the prior content-key.
        try:
            if (
                _abspath_nofollow(src) != _abspath_nofollow(dest)
                and not _is_durable_caas_blob(src)
            ):
                _ensure_symlink(src, dest)
        except OSError:
            logger.debug("CAAS canonical relink failed for %s", src, exc_info=True)
        updated.append(
            ArtifactRef(
                path=str(dest.resolve()),
                kind=ref.kind,
                bytes=dest.stat().st_size if dest.is_file() else ref.bytes,
                sha256=ref.sha256,
            )
        )
    return updated


def _blob_under_entry(candidate: Path, entry_dir: Path) -> Optional[Path]:
    """Return ``candidate`` resolved only when it is a real file inside ``entry_dir``.

    ``Path.is_file()`` follows symlinks, so a stale entry symlink can point outside
    the content-key directory. Always resolve + ``_is_under`` before accepting.
    """
    try:
        if not candidate.is_file():
            return None
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_file() or not _is_under(resolved, entry_dir):
        return None
    return resolved


def _resolve_blob_in_entry(ref_path: Path, entry_dir: Path) -> Optional[Path]:
    """Map an artifact ref to a real file under ``entry_dir`` (CAAS blob)."""
    entry_dir = entry_dir.resolve()
    path = Path(ref_path).expanduser()

    # Already a blob path under this entry (reject leaf symlinks that escape).
    try:
        if path.is_file() and not path.is_symlink():
            under = _blob_under_entry(path, entry_dir)
            if under is not None:
                return under
    except OSError:
        pass

    # Product symlink / path that resolves into this entry.
    under = _blob_under_entry(path, entry_dir)
    if under is not None:
        return under

    # Recover from durable entry layout when the product path was wiped or a prior
    # buggy commit recorded product locations in the CAAS manifest.
    run_rel = _caas_run_relative(path)
    if run_rel is not None:
        under = _blob_under_entry(entry_dir / run_rel, entry_dir)
        if under is not None:
            return under
    # Prefer preserving run_####/name when the abs path contains that segment.
    parts = path.parts
    for i, part in enumerate(parts):
        if part.startswith("run_") and i + 1 < len(parts):
            under = _blob_under_entry(entry_dir / Path(*parts[i:]), entry_dir)
            if under is not None:
                return under
            break
    return _blob_under_entry(entry_dir / path.name, entry_dir)


def _relink_artifacts_from_entry(
    artifacts: Sequence[ArtifactRef],
    entry_dir: Path,
    *,
    output_dir: Optional[Path] = None,
    canonical_paths: Optional[Sequence[Path]] = None,
) -> List[ArtifactRef]:
    """Create symlinks at canonical artifact paths pointing into entry_dir.

    Manifest artifact paths stay on the durable CAAS blobs under ``entry_dir`` so
    ``verify_entry_artifacts`` / skip-replay still work after the product tree is
    wiped. Product locations are restored as relative symlinks when ``output_dir``
    is provided.

    When ``canonical_paths`` is set (first commit, pre-move product locations),
    do not invent new paths under ``output_dir`` for artifacts that never lived
    there (e.g. BAM under sampleDir while output_dir wrongly resolved to study
    configs/).
    """
    entry_dir = entry_dir.resolve()
    canon_abs: Set[Path] = set()
    if canonical_paths:
        canon_abs = {_abspath_nofollow(Path(p)) for p in canonical_paths}
    relinked: List[ArtifactRef] = []
    for ref in artifacts:
        stored = _resolve_blob_in_entry(Path(ref.path), entry_dir)
        if stored is None:
            continue
        try:
            rel = stored.relative_to(entry_dir)
        except ValueError:
            # Defense in depth: skip blobs that somehow escaped entry_dir (e.g. via
            # a stale symlink). Falling back to basename would reintroduce flatten bugs.
            logger.warning(
                "Skipping CAAS artifact outside entry_dir (%s not under %s)",
                stored,
                entry_dir,
            )
            continue
        if output_dir is not None:
            dest_link = Path(output_dir) / rel
            if canon_abs and _abspath_nofollow(dest_link) not in canon_abs:
                dest_link = None
            if dest_link is not None:
                _ensure_symlink(dest_link, stored)
        relinked.append(
            ArtifactRef(
                path=str(stored.resolve()),
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
        reused = existing.model_copy(
            update={
                "artifacts": relinked or existing.artifacts,
                "content_key": content_key,
                "hyperparam_set_id": record.hyperparam_set_id or existing.hyperparam_set_id,
            }
        )
        # Corrupt plan_iterations entries can keep blob files while task_output still
        # points at missing sibling-key paths (or a flattened run_#### layout). Recommit.
        if action_name == "validation.plan_iterations":
            iterations = (existing.task_output or {}).get("iterations") or []
            paths_ok = bool(iterations)
            for item in iterations:
                if not isinstance(item, Mapping):
                    paths_ok = False
                    break
                project_path = item.get("projectPath")
                run_dir = item.get("runDir")
                if project_path and Path(str(project_path)).is_file():
                    continue
                if run_dir and (Path(str(run_dir)) / "project.json").is_file():
                    continue
                paths_ok = False
                break
            if paths_ok:
                return reused
            logger.info(
                "Recommitting %s content_key %s: cached iteration projectPath files missing",
                action_name,
                content_key[:12],
            )
        else:
            return reused

    entry_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else None
    product_paths = _product_artifact_paths(record.artifacts)

    if out_dir is not None and _should_commit_directory(out_dir, record.artifacts):
        moved = _move_tree_into_entry(
            out_dir,
            entry_dir,
            exclude_names={_ACTION_RESULTS_DIRNAME, ".caas"},
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
        relinked = _relink_artifacts_from_entry(
            stored_artifacts,
            entry_dir,
            output_dir=out_dir,
            canonical_paths=product_paths,
        )
    else:
        stored_artifacts = _move_artifacts_into_entry(
            record.artifacts,
            entry_dir,
            output_dir=out_dir,
        )
        relinked = _relink_artifacts_from_entry(
            stored_artifacts,
            entry_dir,
            output_dir=out_dir,
            canonical_paths=product_paths,
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
