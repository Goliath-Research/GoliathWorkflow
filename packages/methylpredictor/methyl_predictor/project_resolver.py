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
    """Resolve a single path to absolute; relative paths are resolved against base_path or cwd."""
    entry = entry.strip()
    if not entry:
        return ""
    p = Path(entry)
    if not p.is_absolute():
        base = Path(base_path).resolve() if base_path else Path.cwd()
        p = base / p
    return str(p.resolve())


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


def _list_file_search_roots(
    base_path: Optional[str],
    project_config_path: Optional[Union[str, Path]],
) -> List[Path]:
    """Ordered roots to resolve relative list paths (e.g. configs/sets.csv): cwd, project parents, samples_base."""
    roots: List[Path] = []
    seen: set[str] = set()

    def add(p: Optional[Path]) -> None:
        if p is None:
            return
        try:
            r = p.resolve()
        except OSError:
            return
        key = str(r)
        if key not in seen:
            seen.add(key)
            roots.append(r)

    # Project file directory first so configs/foo.csv resolves next to the JSON, not cwd.
    if project_config_path:
        pp = Path(project_config_path)
        if pp.is_file():
            parent = pp.parent
            add(parent)
            if parent.name == "configs":
                add(parent.parent)
        elif pp.is_dir():
            add(pp)
    add(Path.cwd())
    if base_path:
        add(Path(base_path))
    return roots


def _find_relative_csv(entry: str, roots: List[Path]) -> Optional[Path]:
    for root in roots:
        cand = root / entry
        if cand.is_file() and cand.suffix.lower() == ".csv":
            return cand
    return None


def _expand_test_paths(
    entries: List[str],
    base_path: Optional[str],
    project_config_path: Optional[Union[str, Path]] = None,
) -> List[str]:
    """
    Expand a list of entries into full sample paths. Each entry is either a path to a .csv file
    (expanded to the list of paths read from the CSV) or a single sample path.

    Relative .csv list files are looked up under cwd, the project JSON's directory (and repo root
    when the project lives under .../configs/), then samples_base_path — not only under samples_base_path,
    so configs like ``test_control_paths: [\"configs/healthy.csv\"]`` resolve next to the project file.
    Other relative paths are resolved against base_path (samples_base_path) as before.
    """
    result: List[str] = []
    roots = _list_file_search_roots(base_path, project_config_path)
    base = Path(base_path).resolve() if base_path else None
    csv_base_arg = str(base) if base else None
    for entry in (e.strip() for e in entries if e and str(e).strip()):
        if not entry:
            continue
        p = Path(entry)
        if p.is_absolute():
            if p.is_file() and p.suffix.lower() == ".csv":
                result.extend(_read_paths_from_csv_file(p, csv_base_arg))
            else:
                result.append(_resolve_one_path(entry, base_path))
            continue
        csv_hit = _find_relative_csv(entry, roots)
        if csv_hit is not None:
            result.extend(_read_paths_from_csv_file(csv_hit, csv_base_arg))
            continue
        if base is not None:
            p_joined = base / entry
            if p_joined.is_file() and p_joined.suffix.lower() == ".csv":
                result.extend(_read_paths_from_csv_file(p_joined, csv_base_arg))
            else:
                result.append(_resolve_one_path(entry, base_path))
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


MULTICLASS_CLASSIFIER_FILENAME = "multiclass-classifier.pkl"


def _get_multiclass_model_path(project: Any, step_cfg: Dict[str, Any], paths: Any) -> Optional[Path]:
    """Return path to multiclass classifier pkl if it exists, else None."""
    explicit = step_cfg.get("multiclass_model_path") or step_cfg.get("model_path")
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
    classifier_dir = getattr(paths, "classifier_dir", None)
    if classifier_dir:
        candidate = Path(classifier_dir) / MULTICLASS_CLASSIFIER_FILENAME
        if candidate.is_file():
            return candidate
    return None


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

    base_path = getattr(project, "samples_base_path", None)
    proj_path_arg: Union[str, Path] = project_path
    # Precedence: (1) CLI/caller test paths, (2) valid config test paths, (3) training data
    if test_control_paths is not None and test_disease_paths is not None:
        control_paths = _expand_test_paths(
            test_control_paths, base_path, project_config_path=proj_path_arg
        )
        disease_paths = _expand_test_paths(
            test_disease_paths, base_path, project_config_path=proj_path_arg
        )
    else:
        base_path = getattr(project, "samples_base_path", None)
        # Canonical keys; accept legacy aliases (healthy_paths/cancer_paths)
        step_control = step_cfg.get("test_control_paths") or step_cfg.get("healthy_paths")
        step_disease = step_cfg.get("test_disease_paths") or step_cfg.get("cancer_paths")
        if step_control is not None and step_disease is not None:
            control_paths = _expand_test_paths(
                step_control, base_path, project_config_path=proj_path_arg
            )
            disease_paths = _expand_test_paths(
                step_disease, base_path, project_config_path=proj_path_arg
            )
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

    # Ensure all paths are absolute before path_remap
    control_paths = [_resolve_one_path(p, base_path) for p in control_paths if p]
    disease_paths = [_resolve_one_path(p, base_path) for p in disease_paths if p]

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
    Build one PredictorConfig per comparison (control/disease projects), or a single
    multi-class config if multiclass-classifier.pkl exists.
    Test sample precedence: (1) Caller test paths (e.g. CLI) supersede all.
    (2) If step_config.predictor has valid test paths (non-empty after expansion), use them.
    (3) Otherwise use training data (project group sample paths).
    Returns list of (PredictorConfig, comparison_label) or [(config, "multiclass")] when multiclass model is used.
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

    paths = project.get_derived_paths()
    base_path = getattr(project, "samples_base_path", None)

    # Prefer multiclass model when present: one config with test_group_paths
    multiclass_path = _get_multiclass_model_path(project, step_cfg, paths)
    if multiclass_path is not None:
        out_dir = str(Path(paths.validator_dir).resolve())
        step_test_groups = step_cfg.get("test_group_paths")
        if step_test_groups and isinstance(step_test_groups, list):
            test_group_paths: List[Dict[str, Any]] = []
            for entry in step_test_groups:
                if not isinstance(entry, dict):
                    continue
                label = entry.get("label") or entry.get("class_name") or str(len(test_group_paths))
                paths_raw = entry.get("paths") or []
                if isinstance(paths_raw, str):
                    paths_raw = [paths_raw]
                expanded = _expand_test_paths(
                    paths_raw, base_path, project_config_path=project_path
                )
                expanded = [_resolve_one_path(p, base_path) for p in expanded if p]
                if project.path_remap:
                    expanded = _apply_path_remap(expanded, project.path_remap)
                test_group_paths.append({"label": label, "paths": expanded})
        else:
            resolved = project.get_resolved_groups()
            test_group_paths = []
            for label, group_paths in resolved:
                paths_list = list(group_paths)
                paths_list = [_resolve_one_path(p, base_path) for p in paths_list if p]
                if project.path_remap:
                    paths_list = _apply_path_remap(paths_list, project.path_remap)
                test_group_paths.append({"label": label, "paths": paths_list})
        base_dict: Dict[str, Any] = {
            "model_path": str(multiclass_path),
            "model_dir": None,
            "output_dir": out_dir,
            "test_control_paths": [],
            "test_disease_paths": [],
            "test_group_paths": test_group_paths,
            "path_remap": project.path_remap,
            "samples_base_path": project.samples_base_path,
            "debug": step_cfg.get("debug", False),
        }
        return [(PredictorConfig(**base_dict), "multiclass")]

    comparisons = project.get_comparisons()
    # Precedence: (1) CLI/caller test paths, (2) valid config test paths, (3) training data
    use_caller_test_paths = (
        test_control_paths is not None and test_disease_paths is not None
    )
    if not use_caller_test_paths:
        step_control = step_cfg.get("test_control_paths") or step_cfg.get("healthy_paths")
        step_disease = step_cfg.get("test_disease_paths") or step_cfg.get("cancer_paths")
    else:
        step_control = None
        step_disease = None
    config_test_control: Optional[List[str]] = None
    config_test_disease: Optional[List[str]] = None
    if step_control is not None and step_disease is not None:
        config_test_control = _expand_test_paths(
            step_control, base_path, project_config_path=project_path
        )
        config_test_disease = _expand_test_paths(
            step_disease, base_path, project_config_path=project_path
        )
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
            control_paths = _expand_test_paths(
                test_control_paths or [],
                base_path,
                project_config_path=project_path,
            )
            disease_paths = _expand_test_paths(
                test_disease_paths or [],
                base_path,
                project_config_path=project_path,
            )
        elif config_test_control is not None and config_test_disease is not None:
            control_paths = list(config_test_control)
            disease_paths = list(config_test_disease)
        else:
            control_paths = list(project.get_group_sample_paths_by_label(spec.control_group))
            disease_paths = list(project.get_group_sample_paths_by_label(spec.disease_group))
        # Ensure all paths are absolute before path_remap
        control_paths = [_resolve_one_path(p, base_path) for p in control_paths if p]
        disease_paths = [_resolve_one_path(p, base_path) for p in disease_paths if p]
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
