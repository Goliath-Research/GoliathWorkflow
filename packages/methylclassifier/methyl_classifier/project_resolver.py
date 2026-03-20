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

# Merged into effective classifier step when predicting default OvR bundle save path.
_CLASSIFIER_STEP_KEYS_FOR_BUNDLE_PATH = (
    "ovr_binary_pickles_from_comparisons",
    "ovr_bundle_filename",
    "ovr_binary_model_paths",
    "ovr_detection_dirs",
    "ovr_pairwise_aggregate_control",
)


def predicted_multiclass_ovr_bundle_path(
    project: ProjectConfig,
    classifier_step: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Default ``save_classifier_path`` location for control/disease multiclass OvR:
    ``<project_root>/classifiers/<control_group>/<bundle>.pkl``.

    Applies when the project has ≥3 resolved groups and the classifier step requests
    OvR (``ovr_binary_pickles_from_comparisons`` or explicit ``ovr_binary_model_paths`` /
    ``ovr_detection_dirs`` with length ≥2). Does not check that the file exists.
    """
    step = dict(
        classifier_step
        if classifier_step is not None
        else (project.get_step_config("classifier") or {})
    )
    if not project.uses_control_disease():
        return None
    resolved = project.get_resolved_groups()
    if len(resolved) < 3:
        return None
    ovr_dirs = step.get("ovr_detection_dirs") or []
    has_ovr = bool(step.get("ovr_binary_pickles_from_comparisons")) or len(
        step.get("ovr_binary_model_paths") or []
    ) >= 2 or len(ovr_dirs) >= 2 or (
        step.get("ovr_pairwise_aggregate_control")
        and len(ovr_dirs) >= 1
    )
    if not has_ovr:
        return None
    ctrl_label = resolved[0][0]
    bundle_fn = step.get("ovr_bundle_filename")
    if bundle_fn:
        fn = str(bundle_fn)
        if not fn.endswith(".pkl"):
            fn = f"{fn}.pkl"
    else:
        fn = f"classifier_{ctrl_label}_{project.project_name}.pkl"
    return Path(project.get_project_root()) / "classifiers" / ctrl_label / fn


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
    return (
        len(p) >= 2
        or len(d) >= 2
        or (bool(step_cfg.get("ovr_pairwise_aggregate_control")) and len(d) >= 1)
    )


def expand_ovr_paths_from_comparisons(
    project: ProjectConfig,
    *,
    unified_basename: str,
    control_vs_rest_pkl: Optional[str] = None,
) -> Tuple[List[str], List[str], bool]:
    """
    Build OvR **detection directory** paths from ``comparisons`` (and optional control override).

    Returns ``(dirs, class_names, pairwise_aggregate_control)``.

    **Default (``pairwise_aggregate_control=True``):** one directory per **disease** in
    ``get_resolved_groups()`` order — ``detections/<control_group>/<disease_group>/`` for each
    comparison (e.g. ``all/pca1``, ``all/pca2``, …). There are **K-1** dirs for **K** class
    names (control label first, then each disease). The control OvR head **aggregates** P(control)
    across those pairwise detectors (no duplicate reuse of ``all/pca1`` for both control and
    pca1).

    **Explicit control directory** (``pairwise_aggregate_control=False``): when
    ``ovr_control_vs_rest_pkl`` is set, or when
    ``detections/one_vs_rest/<control>/<unified_basename>`` exists, the first path is that control
    directory and the following paths are the same per-disease directories as above (**K** dirs
    for **K** names). Ensure the explicit control dir is not identical to a disease dir unless
    intended.

    ``unified_basename`` verifies a detector artifact exists in each directory used.

    ``control_vs_rest_pkl``: existing file (parent dir used) or directory.
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

    disease_dirs: List[str] = []
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
        candidate = det_dir / unified_basename
        if not candidate.is_file():
            raise FileNotFoundError(
                f"OvR: detector artifact not found at {candidate} "
                f"(comparison {spec.control_group!r} vs {spec.disease_group!r}). "
                "Run MethylDetector or adjust ovr_unified_classifier_basename."
            )
        disease_dirs.append(str(det_dir))

    if control_vs_rest_pkl:
        p = Path(control_vs_rest_pkl).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"ovr_control_vs_rest_pkl not found: {p}")
        ctrl_dir = str(p.parent if p.is_file() else p)
        out_dirs = [ctrl_dir] + disease_dirs
        return out_dirs, names, False

    root = Path(project.get_project_root())
    dedicated = root / "detections" / "one_vs_rest" / control_label / unified_basename
    if dedicated.is_file():
        ctrl_dir = str(dedicated.parent)
        out_dirs = [ctrl_dir] + disease_dirs
        return out_dirs, names, False

    # Canonical: K-1 pairwise dirs + synthetic control head from all pairwises
    return disease_dirs, names, True


def _consume_ovr_comparison_options_and_maybe_expand(
    project: ProjectConfig, base: Dict[str, Any]
) -> None:
    """
    Pop resolver-only classifier keys and, if requested, set ovr_detection_dirs (+ names)
    from comparisons. Safe to call when base was built from resolve_classifier_config merge.
    """
    flag = bool(base.pop("ovr_binary_pickles_from_comparisons", False))
    basename = base.pop("ovr_unified_classifier_basename", "classifier-1-CG,CHG,CHH.pkl")
    ctrl_pkl = base.pop("ovr_control_vs_rest_pkl", None)
    if not flag:
        return
    dirs, default_names, agg_ctrl = expand_ovr_paths_from_comparisons(
        project,
        unified_basename=str(basename),
        control_vs_rest_pkl=ctrl_pkl,
    )
    base["ovr_detection_dirs"] = dirs
    base["ovr_pairwise_aggregate_control"] = agg_ctrl
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

    # Default save path: multiclass OvR → classifiers/<control>/<bundle>.pkl; else classifiers root.
    if not base.get("save_classifier_path"):
        merged_cls = dict(project.get_step_config("classifier") or {})
        for k in _CLASSIFIER_STEP_KEYS_FOR_BUNDLE_PATH:
            if k in base:
                merged_cls[k] = base[k]
        p_bundle = predicted_multiclass_ovr_bundle_path(project, merged_cls)
        ovr_paths = base.get("ovr_binary_model_paths") or []
        ovr_dirs = base.get("ovr_detection_dirs") or []
        agg_ovr = bool(base.get("ovr_pairwise_aggregate_control"))
        if p_bundle is not None and (
            len(ovr_paths) >= 2
            or len(ovr_dirs) >= 2
            or (agg_ovr and len(ovr_dirs) >= 1)
        ):
            base["save_classifier_path"] = str(p_bundle)
        else:
            base["save_classifier_path"] = str(
                Path(paths.classifier_dir) / f"{project.project_name}-classifier.pkl"
            )

    base.pop("ovr_bundle_filename", None)

    return ClassificationConfig(**base)
