"""
Resolve MethylPredictor config from a pipeline project config.
Supports control/disease (per-comparison) and flat groups (single run).
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from methyl_utils import load_project

from .models.config import PredictorConfig


def _resolve_one_path(entry: str, base_path: Optional[str]) -> str:
    """Resolve a single path; if base_path set and entry is not absolute, return base_path / entry."""
    entry = entry.strip()
    if not entry:
        return ""
    if base_path and not Path(entry).is_absolute():
        return str(Path(base_path).resolve() / entry)
    return entry


def _read_paths_from_csv_file(csv_path: Path, base_path: Optional[str]) -> List[str]:
    """Read sample paths from a CSV (one column or column named path/sample); resolve relative to base_path."""
    out: List[str] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        key = None
        if reader.fieldnames:
            for name in ("path", "sample", "sample_path"):
                if name in (reader.fieldnames or []):
                    key = name
                    break
            if key is None:
                key = reader.fieldnames[0]
        for row in reader:
            p = row.get(key, "").strip() if key else ""
            if p:
                out.append(_resolve_one_path(p, base_path))
    return out


def _expand_test_paths(entries: List[str], base_path: Optional[str]) -> List[str]:
    """
    Expand a list of entries into full sample paths. Each entry is either a path to a .csv file
    (expanded to the list of paths read from the CSV) or a single sample path. Relative paths
    are resolved against base_path.
    """
    result: List[str] = []
    base = Path(base_path).resolve() if base_path else None
    for entry in (e.strip() for e in entries if e and str(e).strip()):
        if not entry:
            continue
        p = Path(entry)
        if base and not p.is_absolute():
            p = base / p
        if p.is_file() and p.suffix.lower() == ".csv":
            result.extend(_read_paths_from_csv_file(p, str(base) if base else None))
        else:
            result.append(_resolve_one_path(entry, base_path))
    return result


def _apply_path_remap(paths: List[str], path_remap: Optional[Dict[str, str]]) -> List[str]:
    """Apply path_remap (longest matching prefix) to each path."""
    if not path_remap or not paths:
        return list(paths)
    out = []
    for p in paths:
        best_old: Optional[str] = None
        for old_prefix in path_remap:
            if p.startswith(old_prefix) and (best_old is None or len(old_prefix) > len(best_old)):
                best_old = old_prefix
        if best_old is not None:
            new_prefix = path_remap[best_old]
            rest = p[len(best_old) :].lstrip("/")
            p = f"{new_prefix.rstrip('/')}/{rest}" if rest else new_prefix.rstrip("/")
        out.append(p)
    return out


def resolve_predictor_config(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    test_control_paths: Optional[List[str]] = None,
    test_disease_paths: Optional[List[str]] = None,
) -> PredictorConfig:
    """
    Build a single PredictorConfig from project (flat groups: group0 = control, group1 = disease).
    Test sample precedence: (1) Caller test_control_paths/test_disease_paths (e.g. CLI) supersede all.
    (2) If step_config.predictor has valid test_control_paths and test_disease_paths (non-empty after expansion), use them.
    (3) Otherwise use training data (project resolved groups).
    When project uses control/disease + comparisons, consider using
    resolve_predictor_config_per_comparison for one run per comparison.
    """
    project = load_project(project_path)
    step_cfg = (project.get_step_config("predictor") or project.get_step_config("validator") or {}).copy()
    classifier_step = project.get_step_config("classifier") or {}
    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            step_cfg = {**step_cfg, **overrides}

    paths = project.get_derived_paths()
    model_path = step_cfg.get("model_path") or classifier_step.get("save_classifier_path")
    model_dir = step_cfg.get("model_dir")
    if model_path is None and model_dir is None:
        model_dir = paths.detection_dir

    out_dir = output_dir if output_dir is not None else paths.validator_dir
    out_dir = str(Path(out_dir).resolve())

    # Precedence: (1) CLI/caller test paths, (2) valid config test paths, (3) training data
    if test_control_paths is not None and test_disease_paths is not None:
        control_paths = list(test_control_paths)
        disease_paths = list(test_disease_paths)
    else:
        base_path = getattr(project, "samples_base_path", None)
        step_control = step_cfg.get("test_control_paths")
        step_disease = step_cfg.get("test_disease_paths")
        if step_control is not None and step_disease is not None:
            control_paths = _expand_test_paths(step_control, base_path)
            disease_paths = _expand_test_paths(step_disease, base_path)
            if not control_paths or not disease_paths:
                # Config test paths invalid (empty after expansion); fall back to training data
                resolved = project.get_resolved_groups()
                if len(resolved) >= 2:
                    control_paths = list(resolved[0][1])
                    disease_paths = list(resolved[1][1])
        else:
            control_paths = None
            disease_paths = None
        if control_paths is None or disease_paths is None:
            resolved = project.get_resolved_groups()
            if len(resolved) < 2:
                raise ValueError(
                    "Project has fewer than 2 groups; provide test_control_paths and test_disease_paths "
                    "in step_config.predictor or via CLI, or use a project with at least 2 groups."
                )
            control_paths = list(resolved[0][1])
            disease_paths = list(resolved[1][1])

    if project.path_remap:
        control_paths = _apply_path_remap(control_paths, project.path_remap)
        disease_paths = _apply_path_remap(disease_paths, project.path_remap)

    base: Dict[str, Any] = {
        "model_path": model_path,
        "model_dir": model_dir,
        "output_dir": out_dir,
        "test_control_paths": control_paths,
        "test_disease_paths": disease_paths,
        "path_remap": project.path_remap,
        "samples_base_path": project.samples_base_path,
        "debug": step_cfg.get("debug", False),
    }
    return PredictorConfig(**base)


def resolve_predictor_config_per_comparison(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    test_control_paths: Optional[List[str]] = None,
    test_disease_paths: Optional[List[str]] = None,
) -> List[Tuple[PredictorConfig, str]]:
    """
    Build one PredictorConfig per comparison (control/disease projects).
    Test sample precedence: (1) Caller test_control_paths/test_disease_paths (e.g. CLI) supersede all.
    (2) If step_config.predictor has valid test_control_paths and test_disease_paths (non-empty after expansion), use them.
    (3) Otherwise use training data (project group sample paths).
    Returns list of (PredictorConfig, comparison_label).
    """
    project = load_project(project_path)
    if not getattr(project, "uses_control_disease", lambda: False)():
        # Flat groups: single config
        config = resolve_predictor_config(
            project_path,
            step_override_path=step_override_path,
            test_control_paths=test_control_paths,
            test_disease_paths=test_disease_paths,
        )
        return [(config, "validation")]

    step_cfg = (project.get_step_config("predictor") or project.get_step_config("validator") or {}).copy()
    classifier_step = project.get_step_config("classifier") or {}
    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            step_cfg = {**step_cfg, **overrides}

    comparisons = project.get_comparisons()
    paths = project.get_derived_paths()
    base_path = getattr(project, "samples_base_path", None)
    # Precedence: (1) CLI/caller test paths, (2) valid config test paths, (3) training data
    use_caller_test_paths = (
        test_control_paths is not None and test_disease_paths is not None
    )
    step_control = step_cfg.get("test_control_paths") if not use_caller_test_paths else None
    step_disease = step_cfg.get("test_disease_paths") if not use_caller_test_paths else None
    config_test_control: Optional[List[str]] = None
    config_test_disease: Optional[List[str]] = None
    if step_control is not None and step_disease is not None:
        config_test_control = _expand_test_paths(step_control, base_path)
        config_test_disease = _expand_test_paths(step_disease, base_path)
        if not config_test_control or not config_test_disease:
            config_test_control = None
            config_test_disease = None

    result: List[Tuple[PredictorConfig, str]] = []
    for spec in comparisons:
        comp_label = spec.comparison_label or spec.disease_group
        ctrl_label = spec.control_group
        dis_label = spec.disease_group
        classifier_output_dir = project.get_classifier_output_dir(ctrl_label, dis_label)
        detection_dir = project.get_detection_output_dir(ctrl_label, dis_label)
        project_name = getattr(project, "project_name", "classifier")
        full_classifier_pkl = f"{classifier_output_dir}/{project_name}-classifier.pkl"
        if step_cfg.get("model_path") is not None:
            model_path = step_cfg.get("model_path")
            model_dir = None
        elif step_cfg.get("model_dir") is not None:
            model_path = None
            model_dir = step_cfg.get("model_dir")
        elif Path(full_classifier_pkl).is_file():
            model_path = full_classifier_pkl
            model_dir = None
        else:
            model_path = None
            model_dir = detection_dir
        out_dir = project.get_validator_output_dir(ctrl_label, dis_label)

        if use_caller_test_paths:
            control_paths = list(test_control_paths)
            disease_paths = list(test_disease_paths)
        elif config_test_control is not None and config_test_disease is not None:
            control_paths = list(config_test_control)
            disease_paths = list(config_test_disease)
        else:
            control_paths = list(project.get_group_sample_paths_by_label(spec.control_group))
            disease_paths = list(project.get_group_sample_paths_by_label(spec.disease_group))
        if project.path_remap:
            control_paths = _apply_path_remap(control_paths, project.path_remap)
            disease_paths = _apply_path_remap(disease_paths, project.path_remap)

        base: Dict[str, Any] = {
            "model_path": model_path,
            "model_dir": model_dir,
            "output_dir": out_dir,
            "test_control_paths": control_paths,
            "test_disease_paths": disease_paths,
            "path_remap": project.path_remap,
            "samples_base_path": project.samples_base_path,
            "debug": step_cfg.get("debug", False),
        }
        result.append((PredictorConfig(**base), comp_label))
    return result
