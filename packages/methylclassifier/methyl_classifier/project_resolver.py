"""
Resolve MethylClassifier config from a pipeline project config (Pydantic only).
Supports binary (centroid1/centroid2) and N-group multiclass (centroid_dirs + multiclass_class_names).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from methyl_utils import ProjectConfig, load_project

from .models.config_schema import ClassificationConfig

CLASSIFIER_OUTPUT_FILENAME = "classification_results.csv"


def merge_project_classifier_step(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Merged ``step_config.classifier`` dict, including optional JSON overrides."""
    project = load_project(project_path)
    step_cfg = dict(project.get_step_config("classifier") or {})
    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                step_cfg.update(json.load(f))
    return step_cfg


def classifier_step_dict_has_ovr_sources(step_cfg: Dict[str, Any]) -> bool:
    """True if merged classifier step defines K>=2 OvR detector sources."""
    if step_cfg.get("ovr_binary_pickles_from_comparisons"):
        return True
    p = step_cfg.get("ovr_binary_model_paths") or []
    d = step_cfg.get("ovr_detection_dirs") or []
    return len(p) >= 2 or len(d) >= 2


def expand_ovr_paths_from_comparisons(
    project: ProjectConfig,
    *,
    unified_basename: str,
    control_vs_rest_pkl: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """
    Build OvR pickle paths from pipeline layout: ``controls`` / ``diseases`` / ``comparisons``.

    Requires ``uses_control_disease()`` and **exactly one** control group in ``controls.groups``.
    Resolved group order is control label(s) then disease labels (same as ``get_resolved_groups()``).
    For each disease label (after the first resolved entry), there must be a comparison with
    that ``disease_group``; the path is
    ``<project_root>/detections/<control_group>/<disease_group>/<unified_basename>``.

    The first path (control class, one-vs-rest) defaults to
    ``<project_root>/detections/one_vs_rest/<control_label>/<unified_basename>`` unless
    ``control_vs_rest_pkl`` is set.
    """
    if not project.uses_control_disease():
        raise ValueError(
            "ovr_binary_pickles_from_comparisons requires a project with controls, diseases, and comparisons"
        )
    if project.control is None or len(project.control.groups) != 1:
        raise ValueError(
            "ovr_binary_pickles_from_comparisons currently supports exactly one control group"
        )
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        raise ValueError("Project must have at least one control and one disease group")
    comparisons = project.get_comparisons()
    comp_by_disease = {spec.disease_group: spec for spec in comparisons}
    control_label = resolved[0][0]
    names = [label for label, _ in resolved]

    if control_vs_rest_pkl:
        first_path = str(Path(control_vs_rest_pkl).expanduser())
    else:
        first_path = str(
            Path(project.get_project_root())
            / "detections"
            / "one_vs_rest"
            / control_label
            / unified_basename
        )

    out_paths = [first_path]
    for label, _ in resolved[1:]:
        if label not in comp_by_disease:
            raise ValueError(
                f"No comparison with disease_group={label!r} for OvR path; "
                f"check comparisons vs disease groups (have: {sorted(comp_by_disease.keys())})"
            )
        spec = comp_by_disease[label]
        det_dir = Path(
            project.get_detection_output_dir(spec.control_group, spec.disease_group)
        )
        out_paths.append(str(det_dir / unified_basename))

    if len(names) != len(out_paths):
        raise RuntimeError("internal: names and paths length mismatch")
    return out_paths, names


def _consume_ovr_comparison_options_and_maybe_expand(
    project: ProjectConfig, base: Dict[str, Any]
) -> None:
    """
    Pop resolver-only classifier keys and, if requested, set ovr_binary_model_paths (+ names)
    from comparisons. Safe to call when base was built from resolve_classifier_config merge.
    """
    flag = bool(base.pop("ovr_binary_pickles_from_comparisons", False))
    basename = base.pop("ovr_unified_classifier_basename", "classifier-1-CG,CHG,CHH.pkl")
    ctrl_pkl = base.pop("ovr_control_vs_rest_pkl", None)
    if not flag:
        return
    paths, default_names = expand_ovr_paths_from_comparisons(
        project,
        unified_basename=str(basename),
        control_vs_rest_pkl=ctrl_pkl,
    )
    base["ovr_binary_model_paths"] = paths
    if not base.get("ovr_class_names"):
        base["ovr_class_names"] = default_names


def _disease_subdir(project: ProjectConfig) -> str:
    """Middle path segment for step dirs: <step>/<disease_label>/<disease_group>. Uses project.disease.label when set."""
    if project.disease is not None:
        return project.disease.label
    return "cancer"


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

    if project.uses_control_disease():
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
            if not base.get("save_classifier_path"):
                classifier_out_dir = Path(project.get_classifier_output_dir(ctrl_label, dis_label))
                base["save_classifier_path"] = str(
                    classifier_out_dir / f"{project.project_name}-classifier.pkl"
                )
            out.append((ClassificationConfig(**base), comp_label))
        return out

    paths = project.get_derived_paths()
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        return []
    centroid_dirs = paths.centroid_dirs or [paths.centroid1_dir, paths.centroid2_dir]
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
        if not base.get("save_classifier_path"):
            classifier_out_dir = Path(project.get_classifier_output_dir(control_label, label))
            base["save_classifier_path"] = str(
                classifier_out_dir / f"{project.project_name}-classifier.pkl"
            )
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
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        raise ValueError("Project must have at least 2 groups for multiclass")
    centroid_dirs = paths.centroid_dirs or [paths.centroid1_dir, paths.centroid2_dir]
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
    resolved = project.get_resolved_groups()
    centroid_dirs = paths.centroid_dirs

    base = {
        "model_dir": paths.detection_dir,
        "centroid1_dir": paths.centroid1_dir,
        "centroid2_dir": paths.centroid2_dir,
        "output_path": str(Path(paths.classifier_dir) / output_filename),
    }
    if len(centroid_dirs) > 2:
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

    _consume_ovr_comparison_options_and_maybe_expand(project, base)

    # OvR assembly from detector outputs replaces a single shared detection_dir model.
    if base.get("ovr_binary_model_paths") or base.get("ovr_detection_dirs"):
        base["model_dir"] = None
        base["model_path"] = None

    # Default: write combined classifier next to classification CSV under <project>/classifiers/
    if not base.get("save_classifier_path"):
        base["save_classifier_path"] = str(
            Path(paths.classifier_dir) / f"{project.project_name}-classifier.pkl"
        )

    return ClassificationConfig(**base)
