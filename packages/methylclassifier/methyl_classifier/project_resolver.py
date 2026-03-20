"""
Resolve MethylClassifier config from a pipeline project config (Pydantic only).
Supports binary (centroid1/centroid2) and N-group multiclass (centroid_dirs + multiclass_class_names).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from methyl_utils import load_project

from .models.config_schema import ClassificationConfig

CLASSIFIER_OUTPUT_FILENAME = "classification_results.csv"


def _disease_subdir(project: Any) -> str:
    """Middle path segment for step dirs: <step>/<disease_label>/<disease_group>. Uses project.disease.label when set."""
    return project.disease.label if getattr(project, "disease", None) is not None else "cancer"


def resolve_classifier_config_per_cancer_group(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    control_index: int = 0,
    disease_subdir: Optional[str] = None,
) -> List[Tuple[ClassificationConfig, str]]:
    """
    Build one ClassificationConfig per comparison.
    When project uses control/disease + comparisons: one entry per get_comparisons().
    Otherwise: one per non-control group (flat groups).

    Returns:
        List of (config, comparison_label) for each comparison.
    """
    project = load_project(project_path)
    step_cfg = project.get_step_config("classifier") or {}
    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            step_cfg = {**step_cfg, **overrides}

    disease_label = disease_subdir if disease_subdir is not None else _disease_subdir(project)

    if getattr(project, "uses_control_disease", lambda: False)():
        comparisons = project.get_comparisons()
        paths = project.get_derived_paths()
        out: List[Tuple[ClassificationConfig, str]] = []
        for spec in comparisons:
            comp_label = spec.comparison_label or spec.disease_group
            ctrl_label = spec.control_group
            dis_label = spec.disease_group
            model_dir = project.get_detection_output_dir(ctrl_label, dis_label)
            output_path = str(Path(project.get_classifier_output_dir(ctrl_label, dis_label)) / CLASSIFIER_OUTPUT_FILENAME)
            base: Dict[str, Any] = {
                "model_dir": model_dir,
                "model_path": None,
                "centroid1_dir": project.get_centroid_dir("control", ctrl_label),
                "centroid2_dir": project.get_centroid_dir("disease", dis_label),
                "output_path": output_path,
            }
            if project.path_remap:
                base["centroid_path_remap"] = project.path_remap
            for k, v in step_cfg.items():
                base[k] = v
            # Save the combined classifier (with fitted chromosome weights) into the run's classifier
            # output dir so MethylValidator/MethylPredictor finds it.
            project_name = getattr(project, "project_name", "classifier")
            classifier_out_dir = Path(project.get_classifier_output_dir(ctrl_label, dis_label))
            base["save_classifier_path"] = str(classifier_out_dir / f"{project_name}-classifier.pkl")
            out.append((ClassificationConfig(**base), comp_label))
        return out

    paths = project.get_derived_paths()
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        return []
    centroid_dirs = getattr(paths, "centroid_dirs", None) or [paths.centroid1_dir, paths.centroid2_dir]
    if len(centroid_dirs) != len(resolved):
        centroid_dirs = []
        for i, (label, _) in enumerate(resolved):
            side = "control" if i == control_index else "disease"
            centroid_dirs.append(project.get_centroid_dir(side, label))
    c1_dir = centroid_dirs[control_index]
    out = []
    for i in range(len(resolved)):
        if i == control_index:
            continue
        label = resolved[i][0]
        control_label = resolved[control_index][0]
        model_dir = project.get_detection_output_dir(control_label, label)
        output_path = str(Path(project.get_classifier_output_dir(control_label, label)) / CLASSIFIER_OUTPUT_FILENAME)
        base = {
            "model_dir": model_dir,
            "model_path": None,
            "centroid1_dir": c1_dir,
            "centroid2_dir": centroid_dirs[i],
            "output_path": output_path,
        }
        if project.path_remap:
            base["centroid_path_remap"] = project.path_remap
        for k, v in step_cfg.items():
            base[k] = v
        out.append((ClassificationConfig(**base), label))
    return out


def build_multiclass_config_from_project(
    project_path: Union[str, Path],
    dmps_csv: Optional[Union[str, Path]] = None,
    output_model: Optional[Union[str, Path]] = None,
    weights_column: Optional[str] = "importance",
    detection_dmps_glob: str = "dmps-*.csv",
) -> Dict[str, Any]:
    """
    Build a multiclass model config dict from a project (for use with build_multiclass_model).

    Uses the project's resolved groups (centroid_dirs + labels). If dmps_csv is not given,
    looks under the project's detection_dir for a DMP CSV (first file matching detection_dmps_glob).
    For N-class detection you typically run MethylDetector one-vs-rest or merge pairwise DMPs
    and place the merged CSV in detection_dir, or pass dmps_csv explicitly.

    Returns:
        Config dict with keys: dmps_csv, output_model, weights_column, classes (list of {name, centroid_dir}).
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    get_resolved = getattr(project, "get_resolved_groups", None)
    if get_resolved is None:
        raise ValueError("multiclass from project requires methyl_utils with get_resolved_groups (upgrade methylutils)")
    resolved = get_resolved()
    if len(resolved) < 2:
        raise ValueError("Project must have at least 2 groups for multiclass")
    centroid_dirs = getattr(paths, "centroid_dirs", None) or [paths.centroid1_dir, paths.centroid2_dir]
    if len(centroid_dirs) != len(resolved):
        centroid_dirs = []
        for i, (label, _) in enumerate(resolved):
            side = "control" if i == 0 else "disease"
            centroid_dirs.append(project.get_centroid_dir(side, label))

    if dmps_csv is None:
        det_dir = Path(paths.detection_dir)
        if det_dir.exists():
            candidates = sorted(det_dir.glob(detection_dmps_glob))
            if candidates:
                dmps_csv = str(candidates[0])
            else:
                dmps_csv = str(det_dir / "dmps-all-biological.csv")
        else:
            dmps_csv = str(Path(paths.detection_dir) / "dmps-all-biological.csv")
    else:
        dmps_csv = str(Path(dmps_csv).resolve())

    if output_model is None:
        output_model = str(Path(paths.classifier_dir) / "multiclass-classifier.pkl")
    else:
        output_model = str(Path(output_model).resolve())

    classes: List[Dict[str, str]] = []
    for (label, _), cdir in zip(resolved, centroid_dirs):
        classes.append({"name": label, "centroid_dir": str(Path(cdir).resolve())})

    return {
        "dmps_csv": dmps_csv,
        "output_model": output_model,
        "weights_column": weights_column,
        "min_sample_coverage": 10,
        "coverage_weighting": True,
        "classes": classes,
    }


def resolve_classifier_config(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    output_filename: str = "classification_results.csv",
) -> ClassificationConfig:
    """
    Build ClassificationConfig from a project config and optional step overrides.

    Model directory is set to the project's detection_dir (where MethylDetector
    writes trained classifiers). Centroid dirs and path_remap come from the project;
    output goes to classifier_dir.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    get_resolved = getattr(project, "get_resolved_groups", None)
    resolved = get_resolved() if get_resolved is not None else None
    centroid_dirs = getattr(paths, "centroid_dirs", None)

    base = {
        "model_dir": paths.detection_dir,
        "centroid1_dir": paths.centroid1_dir,
        "centroid2_dir": paths.centroid2_dir,
        "output_path": str(Path(paths.classifier_dir) / output_filename),
    }
    if resolved is not None and centroid_dirs and len(centroid_dirs) > 2:
        base["centroid_dirs"] = list(centroid_dirs)
        base["multiclass_class_names"] = [resolved[i][0] for i in range(len(resolved))]
    if project.path_remap:
        base["centroid_path_remap"] = project.path_remap

    # Apply project-level step config (classifier) if present
    step_cfg = project.get_step_config("classifier")
    if step_cfg:
        for k, v in step_cfg.items():
            base[k] = v

    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            for k, v in overrides.items():
                base[k] = v

    # OvR assembly from detector outputs replaces a single shared detection_dir model.
    if base.get("ovr_binary_model_paths") or base.get("ovr_detection_dirs"):
        base["model_dir"] = None
        base["model_path"] = None

    return ClassificationConfig(**base)
