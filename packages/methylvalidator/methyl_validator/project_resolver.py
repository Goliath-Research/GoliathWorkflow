"""
Resolve MethylValidator config from a pipeline project config.
Supports control/disease (per-comparison) and flat groups (single run).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from methyl_utils import load_project

from .models.config import ValidatorConfig


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


def resolve_validator_config(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    test_control_paths: Optional[List[str]] = None,
    test_disease_paths: Optional[List[str]] = None,
) -> ValidatorConfig:
    """
    Build a single ValidatorConfig from project (flat groups: group0 = control, group1 = disease).
    When project uses control/disease + comparisons, consider using
    resolve_validator_config_per_comparison for one run per comparison.
    """
    project = load_project(project_path)
    step_cfg = (project.get_step_config("validator") or {}).copy()
    classifier_step = project.get_step_config("classifier") or {}
    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            step_cfg = {**step_cfg, **overrides}

    paths = project.get_derived_paths()
    # Model: prefer step_config.validator then step_config.classifier then detection_dir
    model_path = step_cfg.get("model_path") or classifier_step.get("save_classifier_path")
    model_dir = step_cfg.get("model_dir")
    if model_path is None and model_dir is None:
        model_dir = paths.detection_dir

    out_dir = output_dir if output_dir is not None else paths.validator_dir
    out_dir = str(Path(out_dir).resolve())

    if test_control_paths is not None and test_disease_paths is not None:
        control_paths = list(test_control_paths)
        disease_paths = list(test_disease_paths)
    else:
        resolved = project.get_resolved_groups()
        if len(resolved) < 2:
            raise ValueError("Project has fewer than 2 groups; provide test_control_paths and test_disease_paths or use a project with at least 2 groups.")
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
    return ValidatorConfig(**base)


def resolve_validator_config_per_comparison(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[ValidatorConfig, str]]:
    """
    Build one ValidatorConfig per comparison (control/disease projects).
    Returns list of (ValidatorConfig, comparison_label).
    """
    project = load_project(project_path)
    if not getattr(project, "uses_control_disease", lambda: False)():
        # Flat groups: single config
        config = resolve_validator_config(project_path, step_override_path=step_override_path)
        return [(config, "validation")]

    step_cfg = (project.get_step_config("validator") or {}).copy()
    classifier_step = project.get_step_config("classifier") or {}
    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            step_cfg = {**step_cfg, **overrides}

    comparisons = project.get_comparisons()
    paths = project.get_derived_paths()

    result: List[Tuple[ValidatorConfig, str]] = []
    for spec in comparisons:
        comp_label = spec.comparison_label or spec.disease_group
        ctrl_label = spec.control_group
        dis_label = spec.disease_group
        classifier_output_dir = project.get_classifier_output_dir(ctrl_label, dis_label)
        detection_dir = project.get_detection_output_dir(ctrl_label, dis_label)
        project_name = getattr(project, "project_name", "classifier")
        full_classifier_pkl = f"{classifier_output_dir}/{project_name}-classifier.pkl"
        # Prefer full classifier pkl in classifier output dir; if missing, use detection dir (per-chrom classifier-*.pkl)
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
        result.append((ValidatorConfig(**base), comp_label))
    return result
