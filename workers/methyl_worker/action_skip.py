"""Signature-based idempotent skip/replay for workflow ACTION execution."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from methyl_domain.action_result import (
    ActionExecutionRecord,
    ArtifactRef,
    action_results_dir,
    artifact_ref_for,
    atomic_write_action_result,
    manifest_path_for,
    read_action_result,
    utc_now,
)
from pydantic import BaseModel

from .action_catalog import ActionCatalogEntry, idempotency_enabled_for
from .action_execution import (
    ActionExecutionResult,
    execution_result_from_output,
    finalize_output,
    load_output_model,
    validate_input,
)
from .collectors import _run_key
from .task_schema_registry import resolve_task_schema_spec
from .task_validation import strip_runtime_input

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_JSON = _REPO_ROOT / "schemas" / "actions" / "catalog.json"
_TASK_SCHEMAS = _REPO_ROOT / "schemas" / "tasks"

_PATH_SUFFIXES = (".json", ".csv", ".tsv", ".h5", ".hdf5", ".bam", ".txt", ".md")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_path_strings(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("/") or value.startswith("~"):
            try:
                return str(Path(value).expanduser().resolve())
            except OSError:
                return value
        return value
    if isinstance(value, dict):
        return {k: _normalize_path_strings(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_path_strings(v) for v in value]
    return value


def compute_action_revision(entry: ActionCatalogEntry) -> str:
    parts: List[str] = []
    if _CATALOG_JSON.is_file():
        parts.append(_sha256_text(_CATALOG_JSON.read_text(encoding="utf-8"))[:16])
    spec = resolve_task_schema_spec(entry.action_name, entry.capability)
    if spec is not None:
        for name in (spec.input_filename, spec.output_filename):
            path = _TASK_SCHEMAS / name
            if path.is_file():
                parts.append(_sha256_text(path.read_text(encoding="utf-8"))[:16])
    release = os.environ.get("METHYL_PIPELINE_RELEASE", "").strip()
    if release:
        parts.append(release)
    return "+".join(parts) if parts else "unknown"


def _load_action_config_slice(entry: ActionCatalogEntry, input_json: Mapping[str, Any]) -> Optional[dict]:
    if not entry.action_config_key:
        return None
    from methyl_utils import load_project
    from methyl_utils.action_config_resolver import resolve_from_task_input

    regulatory: Optional[Mapping[str, Any]] = None
    project = input_json.get("projectPath") or input_json.get("project")
    if project:
        path = Path(str(project))
        if path.is_dir():
            candidates = sorted(path.glob("project*.json"))
            path = candidates[0] if candidates else path / "project.json"
        if path.is_file():
            try:
                regulatory = load_project(str(path)).get_regulatory_config()
            except Exception:
                regulatory = None
    slice_cfg = resolve_from_task_input(
        entry.action_config_key,
        input_json,
        regulatory=regulatory,
    )
    return slice_cfg if slice_cfg else None


def _previous_mc_run_dir(run_dir: Path) -> Optional[Path]:
    if not run_dir.name.startswith("run_"):
        return None
    try:
        n = int(run_dir.name.split("_", 1)[1])
    except (IndexError, ValueError):
        return None
    if n <= 1:
        return None
    prev = run_dir.parent / f"run_{n - 1:04d}"
    return prev if prev.is_dir() else None


def _directory_fingerprint(root: Path, *, max_files: int = 500) -> Optional[str]:
    if not root.is_dir():
        return None
    entries: List[str] = []
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        count += 1
        if count > max_files:
            entries.append("…truncated")
            break
        try:
            st = path.stat()
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        entries.append(f"{rel}:{st.st_size}:{int(st.st_mtime)}")
    if not entries:
        return None
    return _sha256_text("\n".join(entries))[:16]


def _incremental_centroid_extra(input_json: Mapping[str, Any]) -> Optional[dict]:
    project = input_json.get("projectPath") or input_json.get("project")
    if not project:
        return None
    run_dir = Path(str(project)).resolve().parent
    extra: dict[str, Any] = {}
    prev = _previous_mc_run_dir(run_dir)
    if prev is not None:
        extra["previousRunDir"] = str(prev)
        fp = _directory_fingerprint(prev / "centroids")
        if fp:
            extra["previousCentroidsFingerprint"] = fp
    if input_json.get("addSamples") or input_json.get("removeSamples"):
        extra["addSamples"] = input_json.get("addSamples")
        extra["removeSamples"] = input_json.get("removeSamples")
    seed_dir = input_json.get("centroidSeedDir")
    if seed_dir:
        extra["centroidSeedDir"] = str(seed_dir)
        fp = _directory_fingerprint(Path(str(seed_dir)))
        if fp:
            extra["centroidSeedFingerprint"] = fp
    return extra or None


def compute_input_signature(
    entry: ActionCatalogEntry,
    input_json: Mapping[str, Any],
    input_model: BaseModel,
) -> str:
    payload: dict[str, Any] = {
        "action": entry.action_name,
        "input": _normalize_path_strings(input_model.model_dump(mode="json")),
    }
    action_slice = _load_action_config_slice(entry, input_json)
    if action_slice is not None:
        payload["action_config"] = action_slice
    if entry.action_name == "pipeline.centroid":
        extra = _incremental_centroid_extra(input_json)
        if extra:
            payload["incremental"] = extra
    return _sha256_text(_canonical_json(payload))


def _resolve_monte_carlo_runs_root(input_json: Mapping[str, Any]) -> Optional[Path]:
    explicit = input_json.get("monteCarloRunsRoot")
    if explicit:
        return Path(str(explicit)).expanduser().resolve()
    project = input_json.get("projectPath") or input_json.get("project")
    if not project:
        return None
    try:
        from methyl_utils import load_project

        cfg = load_project(str(project))
        return Path(cfg.output_base) / cfg.project_name / "monte_carlo_runs"
    except Exception:
        return None


def resolve_action_output_dir(entry: ActionCatalogEntry, input_json: Mapping[str, Any]) -> Optional[Path]:
    explicit = input_json.get("outputDir")
    if explicit:
        return Path(str(explicit)).expanduser().resolve()

    action = entry.action_name
    if action == "validation.stability":
        mc_root = _resolve_monte_carlo_runs_root(input_json)
        return mc_root / "stability" if mc_root else None

    if action == "validation.plan_iterations":
        return _resolve_monte_carlo_runs_root(input_json)

    if action in {"validation.stability_freeze_readiness", "validation.prepare_freeze_project"}:
        project = input_json.get("projectPath") or input_json.get("project")
        if not project:
            return None
        try:
            from methyl_utils import load_project

            cfg = load_project(str(project))
            root = Path(cfg.output_base) / cfg.project_name
            if action == "validation.prepare_freeze_project":
                prod = input_json.get("productionOutputDir")
                if prod:
                    return Path(str(prod)).expanduser().resolve()
                return root / "monte_carlo_runs" / "production"
            return root
        except Exception:
            return None

    run_dir = input_json.get("runDir")
    if run_dir:
        return Path(str(run_dir)).expanduser().resolve()

    project = input_json.get("projectPath") or input_json.get("project")
    if project:
        path = Path(str(project)).expanduser().resolve()
        if path.is_file():
            return path.parent
        return path

    return None


def _path_like_output_values(output_dict: Mapping[str, Any]) -> List[Path]:
    paths: List[Path] = []
    for val in output_dict.values():
        if not isinstance(val, str):
            continue
        if not (val.startswith("/") or val.endswith(_PATH_SUFFIXES)):
            continue
        p = Path(val)
        if p.is_file():
            paths.append(p)
    return paths


def _is_action_result_envelope(path: Path) -> bool:
    """Manifest JSON under .action_results/ — not a product artifact."""
    return path.parent.name == ".action_results" and path.suffix == ".json"


def artifacts_from_output(output_dict: Mapping[str, Any]) -> List[ArtifactRef]:
    refs: List[ArtifactRef] = []
    seen: set[str] = set()
    for path in _path_like_output_values(output_dict):
        if _is_action_result_envelope(path):
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        refs.append(artifact_ref_for(path))
    return refs


def compute_output_signature(artifacts: List[ArtifactRef]) -> str:
    if not artifacts:
        return _sha256_text("")
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
    return _sha256_text("\n".join(parts))


# Actions whose success is meaningless without an on-disk output artifact.
# An empty artifact list for these indicates a false-success manifest (the CLI
# reported exit 0 but wrote nothing at outputDir), which must not be replayed.
_ARTIFACT_REQUIRED_ACTIONS = frozenset({"pipeline.centroid"})


def _requires_output_artifacts(entry: ActionCatalogEntry) -> bool:
    return entry.action_name in _ARTIFACT_REQUIRED_ACTIONS


def verify_artifacts(artifacts: List[ArtifactRef]) -> bool:
    for ref in artifacts:
        path = Path(ref.path)
        if _is_action_result_envelope(path):
            continue
        if not path.is_file():
            return False
        if ref.bytes is not None:
            try:
                if path.stat().st_size != ref.bytes:
                    return False
            except OSError:
                return False
    return True


def _force_rerun_requested(input_json: Mapping[str, Any]) -> bool:
    if input_json.get("forceRerun") is True:
        return True
    if os.environ.get("METHYL_FORCE_RERUN", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return False


def _read_manifest(manifest_path: Path) -> Optional[ActionExecutionRecord]:
    if not manifest_path.is_file():
        return None
    try:
        return read_action_result(manifest_path, ActionExecutionRecord)
    except Exception:
        logger.debug("could not read action manifest %s", manifest_path, exc_info=True)
        return None


def _replay_result(
    entry: ActionCatalogEntry,
    record: ActionExecutionRecord,
    *,
    manifest_path: Path,
) -> ActionExecutionResult:
    output_model = load_output_model(entry)
    merged = dict(record.task_output)
    merged.setdefault("action_name", entry.action_name)
    merged.setdefault("capability", entry.capability)
    merged["status"] = "skipped"
    merged["manifest_path"] = str(manifest_path)
    merged["started_at_utc"] = utc_now()
    merged["finished_at_utc"] = utc_now()
    merged["duration_ms"] = 0
    if "artifacts" not in merged:
        merged["artifacts"] = [a.model_dump(mode="json") for a in record.artifacts]
    output = output_model.model_validate(merged)
    return execution_result_from_output(output)


def maybe_skip_action(
    entry: ActionCatalogEntry,
    input_json: Mapping[str, Any],
) -> Optional[ActionExecutionResult]:
    if not idempotency_enabled_for(entry):
        return None
    if _force_rerun_requested(input_json):
        return None

    output_dir = resolve_action_output_dir(entry, input_json)
    if output_dir is None:
        return None

    run_key = _run_key(input_json)
    manifest_path = manifest_path_for(output_dir, entry.action_name, run_key)
    record = _read_manifest(manifest_path)
    if record is None or record.result_code != 0:
        return None

    task_input = strip_runtime_input(dict(input_json))
    try:
        input_model = validate_input(entry, task_input)
    except Exception:
        return None

    current_revision = compute_action_revision(entry)
    current_input_sig = compute_input_signature(entry, dict(input_json), input_model)

    if record.action_revision != current_revision:
        return None
    if record.input_signature != current_input_sig:
        return None
    if not verify_artifacts(record.artifacts):
        return None
    if record.output_signature != compute_output_signature(record.artifacts):
        return None
    product_artifacts = [
        a for a in record.artifacts if not _is_action_result_envelope(Path(a.path))
    ]
    if not product_artifacts and _requires_output_artifacts(entry):
        logger.info(
            "Not skipping %s: manifest %s recorded zero output artifacts (cannot verify success)",
            entry.action_name,
            manifest_path,
        )
        return None

    if entry.action_name == "validation.plan_iterations" and output_dir is not None:
        try:
            from methyl_validation.project_gen import monte_carlo_runs_have_legacy_projects

            if monte_carlo_runs_have_legacy_projects(output_dir):
                logger.info(
                    "Not skipping %s: legacy step_config found under %s",
                    entry.action_name,
                    output_dir,
                )
                return None
        except Exception:
            logger.debug("legacy MC run scan failed for %s", output_dir, exc_info=True)

    logger.info(
        "Skipping %s (signature match, manifest %s)",
        entry.action_name,
        manifest_path,
    )
    return _replay_result(entry, record, manifest_path=manifest_path)


def record_action_execution(
    entry: ActionCatalogEntry,
    input_json: Mapping[str, Any],
    input_model: BaseModel,
    result: ActionExecutionResult,
    *,
    skipped: bool = False,
    skip_reason: Optional[str] = None,
) -> None:
    if not idempotency_enabled_for(entry):
        return

    output_dir = resolve_action_output_dir(entry, input_json)
    if output_dir is None:
        return

    run_key = _run_key(input_json)
    manifest_path = manifest_path_for(output_dir, entry.action_name, run_key)
    output_dict = result.output.model_dump(mode="json")
    task_input = strip_runtime_input(dict(input_json))

    telemetry_keys = {
        "schema_version",
        "action_name",
        "capability",
        "started_at_utc",
        "finished_at_utc",
        "duration_ms",
        "result_code",
        "exit_code",
        "manifest_path",
        "artifacts",
        "status",
    }
    task_output = {k: v for k, v in output_dict.items() if k not in telemetry_keys}

    started = output_dict.get("started_at_utc") or utc_now()
    finished = output_dict.get("finished_at_utc") or utc_now()
    if isinstance(started, str):
        started = datetime.fromisoformat(started.replace("Z", "+00:00"))
    if isinstance(finished, str):
        finished = datetime.fromisoformat(finished.replace("Z", "+00:00"))

    artifacts = artifacts_from_output(output_dict)
    if not artifacts and output_dict.get("artifacts"):
        artifacts = [ArtifactRef.model_validate(a) for a in output_dict["artifacts"]]

    record = ActionExecutionRecord(
        action_name=entry.action_name,
        capability=entry.capability,
        started_at_utc=started,
        finished_at_utc=finished,
        duration_ms=int(output_dict.get("duration_ms") or 0),
        result_code=result.result_code,
        exit_code=int(output_dict.get("exit_code") or 0),
        manifest_path=str(manifest_path),
        artifacts=artifacts,
        action_revision=compute_action_revision(entry),
        input_signature=compute_input_signature(entry, dict(input_json), input_model),
        output_signature=compute_output_signature(artifacts),
        skipped=skipped,
        skip_reason=skip_reason,
        task_output=task_output,
    )

    try:
        action_results_dir(output_dir).mkdir(parents=True, exist_ok=True)
        atomic_write_action_result(manifest_path, record)
    except Exception:
        logger.debug("action manifest write failed for %s", entry.action_name, exc_info=True)

