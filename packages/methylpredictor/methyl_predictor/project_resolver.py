"""
Resolve MethylPredictor config from a pipeline project config.
Supports control/disease (per-comparison) and flat groups (single run).

Predictor test cohorts use the same JSON shape as the project root: ``controls`` and ``diseases``
each with ``label`` and ``groups[{label, sample_paths}]``. Omitted predictor sides fall back to
the top-level project ``controls`` / ``diseases``.
"""

import copy
import csv
import json
import warnings
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from methyl_utils import DerivedPaths, ProjectConfig, load_project
from pydantic import BaseModel

from .models.config import PredictorConfig


_CLASSIFIER_SNAPSHOT_KEYS = (
    "temperature",
    "enable_platt_calibration",
    "use_isotonic_calibration",
    "trimmed_percentile_low",
    "trimmed_percentile_high",
    "weight_method",
    "weight_fit_regularization",
    "weight_fit_alpha",
    "weight_fit_l1_ratio",
    "use_elasticnet_stacking",
    "chromosome_weights",
)


def _classifier_step_snapshot(classifier_step: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not classifier_step:
        return None
    out = {k: classifier_step[k] for k in _CLASSIFIER_SNAPSHOT_KEYS if k in classifier_step}
    return out or None


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


def _apply_binary_cli_paths_to_multiclass_config(
    cfg: PredictorConfig,
    project: ProjectConfig,
    test_control_paths: List[str],
    test_disease_paths: List[str],
    base_path: Optional[str],
    project_path: Union[str, Path],
    path_remap: Optional[Dict[str, str]],
) -> None:
    """
    Methyl-validation (and ``--test-control`` / ``--test-disease``) pass binary validation CSVs even when
    the on-disk model is multiclass/OvR. Without this merge, ``resolve_predictor_config_per_comparison``
    would keep ``test_group_paths`` from the project (training cohorts) and ignore CLI paths.
    """
    expanded_c = _expand_test_paths(
        list(test_control_paths), base_path, project_config_path=project_path
    )
    expanded_c = [_resolve_one_path(p, base_path) for p in expanded_c if p]
    expanded_d = _expand_test_paths(
        list(test_disease_paths), base_path, project_config_path=project_path
    )
    expanded_d = [_resolve_one_path(p, base_path) for p in expanded_d if p]
    if path_remap:
        expanded_c = _apply_path_remap(expanded_c, path_remap)
        expanded_d = _apply_path_remap(expanded_d, path_remap)
    if not expanded_c or not expanded_d:
        return

    comparisons = project.get_comparisons()
    if comparisons:
        spec = comparisons[0]
        ctrl_label = spec.control_group or "control"
        dis_label = spec.disease_group or "disease"
    else:
        ctrl_label, dis_label = "control", "disease"

    cfg.test_group_paths = [
        {"label": str(ctrl_label), "paths": expanded_c, "class_index": 0},
        {"label": str(dis_label), "paths": expanded_d, "class_index": 1},
    ]
    mc_lineage: List[Dict[str, str]] = []
    for p in expanded_c:
        mc_lineage.append(
            {"absolute_path": p, "side": "multiclass", "group_label": str(ctrl_label)}
        )
    for p in expanded_d:
        mc_lineage.append(
            {"absolute_path": p, "side": "multiclass", "group_label": str(dis_label)}
        )
    cfg.sample_lineage = mc_lineage


def _control_disease_side_to_dict(side: Any) -> Dict[str, Any]:
    """Serialize ControlDiseaseSide (or dict) to JSON-friendly dict."""
    if side is None:
        return {"label": "", "groups": []}
    if isinstance(side, dict):
        return copy.deepcopy(side)
    if isinstance(side, BaseModel):
        return side.model_dump(mode="json")
    raise TypeError(
        f"Expected control/disease side to be dict-like or Pydantic model, got {type(side)!r}"
    )


def _effective_predictor_side(
    step_cfg: Dict[str, Any],
    project: ProjectConfig,
    side_key: Literal["controls", "diseases"],
) -> Dict[str, Any]:
    """
    Merge predictor step with project root: use step_config.predictor.<side> if it has
    non-empty ``groups``; otherwise use project.control / project.disease.
    """
    raw = step_cfg.get(side_key)
    if isinstance(raw, dict):
        groups = raw.get("groups")
        if isinstance(groups, list) and len(groups) > 0:
            return copy.deepcopy(raw)
    proj_side = project.control if side_key == "controls" else project.disease
    if proj_side is not None:
        return _control_disease_side_to_dict(proj_side)
    proj_key = "controls" if side_key == "controls" else "diseases"
    raise ValueError(
        f'step_config.predictor.{side_key} must define non-empty "groups", '
        f"or set top-level project {proj_key}."
    )


def _expand_side_group_paths(
    side: Dict[str, Any],
    base_path: Optional[str],
    project_path: Union[str, Path],
    path_remap: Optional[Dict[str, str]],
) -> Dict[str, List[str]]:
    """Map group label -> expanded absolute sample paths (disease ``stages`` → leaf ``type_stage``)."""
    out: Dict[str, List[str]] = {}
    for g in side.get("groups") or []:
        if not isinstance(g, dict):
            continue
        parent = g.get("label")
        if not parent:
            continue
        stages = g.get("stages")
        if isinstance(stages, list) and stages:
            for st in stages:
                if not isinstance(st, dict) or not st.get("label"):
                    continue
                leaf = f"{parent}_{st['label']}"
                raw = st.get("sample_paths") or []
                if isinstance(raw, str):
                    raw = [raw]
                expanded = _expand_test_paths(list(raw), base_path, project_config_path=project_path)
                expanded = [_resolve_one_path(p, base_path) for p in expanded if p]
                if path_remap:
                    expanded = _apply_path_remap(expanded, path_remap)
                out[str(leaf)] = expanded
            continue
        raw = g.get("sample_paths") or []
        if isinstance(raw, str):
            raw = [raw]
        expanded = _expand_test_paths(list(raw), base_path, project_config_path=project_path)
        expanded = [_resolve_one_path(p, base_path) for p in expanded if p]
        if path_remap:
            expanded = _apply_path_remap(expanded, path_remap)
        out[str(parent)] = expanded
    return out


def _expand_side_group_paths_in_order(
    side: Dict[str, Any],
    base_path: Optional[str],
    project_path: Union[str, Path],
    path_remap: Optional[Dict[str, str]],
) -> List[List[str]]:
    """
    Same expansion as :func:`_expand_side_group_paths`, but return one path list per leaf in
    walk order (control/disease groups, then stages) without using composite leaf keys. Used to
    align predictor list files with :func:`ProjectConfig._get_resolved_groups_with_side` labels
    when predictor parent labels differ from top-level cohort JSON (e.g. ``pca`` vs ``prostate_cancer``).
    Order matches ``ProjectConfig._get_resolved_groups_with_side`` (control leaves, then disease).
    """
    out: List[List[str]] = []
    for g in side.get("groups") or []:
        if not isinstance(g, dict) or not g.get("label"):
            continue
        stages = g.get("stages")
        if isinstance(stages, list) and stages:
            for st in stages:
                if not isinstance(st, dict) or not st.get("label"):
                    continue
                raw = st.get("sample_paths") or []
                if isinstance(raw, str):
                    raw = [raw]
                expanded = _expand_test_paths(list(raw), base_path, project_config_path=project_path)
                expanded = [_resolve_one_path(p, base_path) for p in expanded if p]
                if path_remap:
                    expanded = _apply_path_remap(expanded, path_remap)
                out.append(expanded)
            continue
        raw = g.get("sample_paths") or []
        if isinstance(raw, str):
            raw = [raw]
        expanded = _expand_test_paths(list(raw), base_path, project_config_path=project_path)
        expanded = [_resolve_one_path(p, base_path) for p in expanded if p]
        if path_remap:
            expanded = _apply_path_remap(expanded, path_remap)
        out.append(expanded)
    return out


def _resolved_leaf_labels_from_side(side: Dict[str, Any]) -> List[str]:
    """Flatten ``groups`` to centroid leaf labels (``stages`` → ``parent_child``)."""
    out: List[str] = []
    for g in side.get("groups") or []:
        if not isinstance(g, dict) or not g.get("label"):
            continue
        plab = str(g["label"])
        if g.get("stages"):
            for st in g.get("stages") or []:
                if isinstance(st, dict) and st.get("label"):
                    out.append(f"{plab}_{st['label']}")
        else:
            out.append(plab)
    return out


def _filter_side_report(side: Dict[str, Any], group_labels: List[str]) -> Dict[str, Any]:
    """Keep only listed group labels (order = group_labels order); supports nested ``stages`` leaves."""
    by_label: Dict[str, Any] = {}
    for g in side.get("groups") or []:
        if not isinstance(g, dict):
            continue
        plab = g.get("label")
        if not plab:
            continue
        if g.get("stages"):
            for st in g.get("stages") or []:
                if isinstance(st, dict) and st.get("label"):
                    leaf = f"{plab}_{st['label']}"
                    by_label[leaf] = {"label": leaf, "sample_paths": list(st.get("sample_paths") or [])}
        else:
            by_label[plab] = copy.deepcopy(g)
    groups = []
    for lab in group_labels:
        if lab in by_label:
            groups.append(copy.deepcopy(by_label[lab]))
    return {"label": side.get("label", ""), "groups": groups}


def _collect_paths_and_lineage(
    side_name: Literal["control", "disease", "blind"],
    group_labels_in_order: List[str],
    label_to_paths: Dict[str, List[str]],
) -> Tuple[List[str], List[Dict[str, str]]]:
    paths_out: List[str] = []
    lineage: List[Dict[str, str]] = []
    for glabel in group_labels_in_order:
        if glabel not in label_to_paths:
            avail = sorted(label_to_paths.keys())
            raise ValueError(
                f"Predictor {side_name} group {glabel!r} not found. Available labels: {avail}"
            )
        for p in label_to_paths[glabel]:
            paths_out.append(p)
            lineage.append(
                {
                    "absolute_path": p,
                    "side": side_name,
                    "group_label": glabel,
                }
            )
    return paths_out, lineage


def _predictor_blind_has_groups(step_cfg: Dict[str, Any]) -> bool:
    b = step_cfg.get("blind")
    if not isinstance(b, dict):
        return False
    g = b.get("groups")
    return isinstance(g, list) and len(g) > 0


def _assert_predictor_blind_exclusive(step_cfg: Dict[str, Any]) -> None:
    """Blind cohort cannot be combined with explicit labeled predictor.controls / .diseases."""
    for key in ("controls", "diseases"):
        side = step_cfg.get(key)
        if isinstance(side, dict):
            grp = side.get("groups")
            if isinstance(grp, list) and len(grp) > 0:
                raise ValueError(
                    f'step_config.predictor.{key} has non-empty "groups" while "blind" is also set; '
                    "use either labeled (controls+diseases) or blind, not both."
                )


def _build_blind_predictor_dict(
    *,
    step_cfg: Dict[str, Any],
    project: ProjectConfig,
    project_path: Union[str, Path],
    base_path: Optional[str],
    output_dir: str,
    model_path: Optional[str],
    model_dir: Optional[str],
    comparison_label: Optional[str],
) -> Dict[str, Any]:
    """Shared PredictorConfig kwargs for a blind-only run."""
    blind_side = copy.deepcopy(step_cfg["blind"])
    if not isinstance(blind_side, dict):
        raise ValueError('step_config.predictor.blind must be an object with "groups".')
    wrap = {
        "label": blind_side.get("label") or "",
        "groups": blind_side.get("groups") or [],
    }
    bmap = _expand_side_group_paths(wrap, base_path, project_path, project.path_remap)
    labels = [
        str(g.get("label"))
        for g in (wrap.get("groups") or [])
        if isinstance(g, dict) and g.get("label")
    ]
    blind_paths, lineage = _collect_paths_and_lineage("blind", labels, bmap)
    tree = project.cohort_tree_dict()
    return {
        "model_path": model_path,
        "model_dir": model_dir,
        "output_dir": output_dir,
        "test_control_paths": [],
        "test_disease_paths": [],
        "test_blind_paths": blind_paths,
        "path_remap": project.path_remap,
        "samples_base_path": project.samples_base_path,
        "debug": step_cfg.get("debug", False),
        "comparison_label": comparison_label,
        "report_controls": None,
        "report_diseases": None,
        "report_blind": blind_side,
        "blind": blind_side,
        "sample_lineage": lineage,
        "cohort_hierarchy": tree or None,
        "panel": step_cfg.get("panel") if isinstance(step_cfg.get("panel"), dict) else None,
        "classifier_step_snapshot": _classifier_step_snapshot(project.get_step_config("classifier") or {}),
    }


MULTICLASS_CLASSIFIER_FILENAME = "multiclass-classifier.pkl"


def _get_multiclass_model_path(
    project: ProjectConfig,
    step_cfg: Dict[str, Any],
    paths: DerivedPaths,
) -> Optional[Path]:
    """Return path to multiclass classifier pkl if it exists, else None."""
    explicit = step_cfg.get("multiclass_model_path") or step_cfg.get("model_path")
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
    classifier_step = project.get_step_config("classifier") or {}
    classifier_dir = paths.classifier_dir
    # Prefer native merged multiclass PKL (detector export) over OvR bundle when both exist.
    if classifier_dir:
        native_mc = Path(classifier_dir) / MULTICLASS_CLASSIFIER_FILENAME
        if native_mc.is_file():
            return native_mc
    scp = classifier_step.get("save_classifier_path")
    if scp and Path(scp).is_file():
        return Path(scp)
    try:
        from methyl_classifier.project_resolver import predicted_multiclass_ovr_bundle_path

        bundled = predicted_multiclass_ovr_bundle_path(project, classifier_step)
        if bundled is not None and bundled.is_file():
            return bundled
    except ImportError:
        pass
    if classifier_dir:
        project_name = project.project_name
        if project_name:
            legacy = Path(classifier_dir) / f"{project_name}-classifier.pkl"
            if legacy.is_file():
                return legacy
    return None


def _build_multiclass_predictor_config(
    *,
    project: ProjectConfig,
    step_cfg: Dict[str, Any],
    paths: DerivedPaths,
    base_path: Optional[str],
    project_path: Union[str, Path],
    out_dir: str,
) -> PredictorConfig:
    """Single multiclass PredictorConfig from project (training test_group_paths from config or resolved groups)."""
    multiclass_path = _get_multiclass_model_path(project, step_cfg, paths)
    if multiclass_path is None:
        raise ValueError("internal: multiclass classifier path required")
    out_resolved = str(Path(out_dir).resolve())
    step_test_groups = step_cfg.get("test_group_paths")
    mc_lineage: List[Dict[str, str]] = []
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
            for p in expanded:
                mc_lineage.append(
                    {"absolute_path": p, "side": "multiclass", "group_label": str(label)}
                )
    else:
        test_group_paths = []
        pr = project.path_remap
        used_predictor_sides = False
        if project.uses_control_disease():
            ctrl_side = _effective_predictor_side(step_cfg, project, "controls")
            dis_side = _effective_predictor_side(step_cfg, project, "diseases")
            c_order = _expand_side_group_paths_in_order(
                ctrl_side, base_path, project_path, pr
            )
            d_order = _expand_side_group_paths_in_order(
                dis_side, base_path, project_path, pr
            )
            with_side = project._get_resolved_groups_with_side()
            ctrl_res = [(l, p) for l, p, s in with_side if s == "control"]
            dis_res = [(l, p) for l, p, s in with_side if s == "disease"]
            if (
                len(c_order) == len(ctrl_res)
                and len(d_order) == len(dis_res)
                and (c_order or d_order)
            ):
                used_predictor_sides = True
                for (label, _), paths_list in zip(ctrl_res, c_order):
                    test_group_paths.append({"label": label, "paths": paths_list})
                    for p in paths_list:
                        mc_lineage.append(
                            {
                                "absolute_path": p,
                                "side": "multiclass",
                                "group_label": str(label),
                            }
                        )
                for (label, _), paths_list in zip(dis_res, d_order):
                    test_group_paths.append({"label": label, "paths": paths_list})
                    for p in paths_list:
                        mc_lineage.append(
                            {
                                "absolute_path": p,
                                "side": "multiclass",
                                "group_label": str(label),
                            }
                        )
        if not used_predictor_sides:
            resolved = project.get_resolved_groups()
            for label, group_paths in resolved:
                raw = [str(p).strip() for p in group_paths if p and str(p).strip()]
                expanded = _expand_test_paths(raw, base_path, project_config_path=project_path)
                paths_list = [_resolve_one_path(p, base_path) for p in expanded if p]
                if project.path_remap:
                    paths_list = _apply_path_remap(paths_list, project.path_remap)
                test_group_paths.append({"label": label, "paths": paths_list})
                for p in paths_list:
                    mc_lineage.append(
                        {"absolute_path": p, "side": "multiclass", "group_label": str(label)}
                    )
    tree = project.cohort_tree_dict()
    base_dict: Dict[str, Any] = {
        "model_path": str(multiclass_path),
        "model_dir": None,
        "output_dir": out_resolved,
        "test_control_paths": [],
        "test_disease_paths": [],
        "test_group_paths": test_group_paths,
        "path_remap": project.path_remap,
        "samples_base_path": project.samples_base_path,
        "debug": step_cfg.get("debug", False),
        "comparison_label": "multiclass",
        "report_controls": None,
        "report_diseases": None,
        "sample_lineage": mc_lineage,
        "cohort_hierarchy": tree or None,
        "panel": step_cfg.get("panel") if isinstance(step_cfg.get("panel"), dict) else None,
        "classifier_step_snapshot": _classifier_step_snapshot(project.get_step_config("classifier") or {}),
    }
    return PredictorConfig(**base_dict)


def resolve_predictor_config(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    test_control_paths: Optional[List[str]] = None,
    test_disease_paths: Optional[List[str]] = None,
) -> PredictorConfig:
    """
    Build a single PredictorConfig from project (non-comparison / flat layout).

    Test cohorts come from ``step_config.predictor.controls`` / ``.diseases`` (same shape as project
    root), merged with top-level ``controls``/``diseases`` when predictor omits a side.

    Optional CLI override: when both ``test_control_paths`` and ``test_disease_paths`` are passed,
    they are expanded as flat lists (no nested report shape).
    """
    project = load_project(project_path)
    step_cfg = (project.get_step_config("predictor") or {}).copy()
    if not step_cfg:
        legacy_validator = (project.get_step_config("validator") or {}).copy()
        if legacy_validator:
            warnings.warn(
                "step_config.validator is deprecated; use step_config.predictor instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            step_cfg = legacy_validator
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

    base_path = project.samples_base_path
    proj_path_arg: Union[str, Path] = project_path

    if test_control_paths is not None and test_disease_paths is not None:
        control_paths = _expand_test_paths(
            test_control_paths, base_path, project_config_path=proj_path_arg
        )
        disease_paths = _expand_test_paths(
            test_disease_paths, base_path, project_config_path=proj_path_arg
        )
        control_paths = [_resolve_one_path(p, base_path) for p in control_paths if p]
        disease_paths = [_resolve_one_path(p, base_path) for p in disease_paths if p]
        if project.path_remap:
            control_paths = _apply_path_remap(control_paths, project.path_remap)
            disease_paths = _apply_path_remap(disease_paths, project.path_remap)
        lineage: List[Dict[str, str]] = []
        for p in control_paths:
            lineage.append({"absolute_path": p, "side": "control", "group_label": "cli"})
        for p in disease_paths:
            lineage.append({"absolute_path": p, "side": "disease", "group_label": "cli"})
        return PredictorConfig(
            model_path=model_path,
            model_dir=model_dir,
            output_dir=out_dir,
            test_control_paths=control_paths,
            test_disease_paths=disease_paths,
            path_remap=project.path_remap,
            samples_base_path=project.samples_base_path,
            debug=step_cfg.get("debug", False),
            comparison_label=None,
            report_controls={"label": "control", "groups": [{"label": "cli", "sample_paths": []}]},
            report_diseases={"label": "disease", "groups": [{"label": "cli", "sample_paths": []}]},
            sample_lineage=lineage,
            panel=step_cfg.get("panel") if isinstance(step_cfg.get("panel"), dict) else None,
            classifier_step_snapshot=_classifier_step_snapshot(classifier_step),
        )

    if _predictor_blind_has_groups(step_cfg):
        _assert_predictor_blind_exclusive(step_cfg)
        blind_kwargs = _build_blind_predictor_dict(
            step_cfg=step_cfg,
            project=project,
            project_path=proj_path_arg,
            base_path=base_path,
            output_dir=out_dir,
            model_path=model_path,
            model_dir=model_dir,
            comparison_label=None,
        )
        return PredictorConfig(**blind_kwargs)

    if not project.uses_control_disease():
        multiclass_path = _get_multiclass_model_path(project, step_cfg, paths)
        if multiclass_path is not None:
            return _build_multiclass_predictor_config(
                project=project,
                step_cfg=step_cfg,
                paths=paths,
                base_path=base_path,
                project_path=proj_path_arg,
                out_dir=out_dir,
            )

    controls_side = _effective_predictor_side(step_cfg, project, "controls")
    diseases_side = _effective_predictor_side(step_cfg, project, "diseases")
    ctrl_map = _expand_side_group_paths(controls_side, base_path, proj_path_arg, project.path_remap)
    dis_map = _expand_side_group_paths(diseases_side, base_path, proj_path_arg, project.path_remap)
    ctrl_labels = _resolved_leaf_labels_from_side(controls_side)
    dis_labels = _resolved_leaf_labels_from_side(diseases_side)
    control_paths, lin_c = _collect_paths_and_lineage("control", ctrl_labels, ctrl_map)
    disease_paths, lin_d = _collect_paths_and_lineage("disease", dis_labels, dis_map)
    lineage = lin_c + lin_d

    tree = project.cohort_tree_dict()
    base: Dict[str, Any] = {
        "model_path": model_path,
        "model_dir": model_dir,
        "output_dir": out_dir,
        "test_control_paths": control_paths,
        "test_disease_paths": disease_paths,
        "path_remap": project.path_remap,
        "samples_base_path": project.samples_base_path,
        "debug": step_cfg.get("debug", False),
        "comparison_label": None,
        "report_controls": controls_side,
        "report_diseases": diseases_side,
        "sample_lineage": lineage,
        "cohort_hierarchy": tree or None,
        "panel": step_cfg.get("panel") if isinstance(step_cfg.get("panel"), dict) else None,
        "classifier_step_snapshot": _classifier_step_snapshot(classifier_step),
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
    Test sample precedence: (1) Caller test paths (e.g. CLI) supersede all — for multiclass
    PKL, ``--test-control`` + ``--test-disease`` replace default ``test_group_paths`` with two
    cohorts (class indices 0 and 1). (2) Else step_config.predictor test paths when set.
    (3) Else training cohorts from the project.
    Returns list of (PredictorConfig, comparison_label) or [(config, "multiclass")] when multiclass model is used.
    """
    project = load_project(project_path)
    if not project.uses_control_disease():
        # Flat groups: single config
        config = resolve_predictor_config(
            project_path,
            step_override_path=step_override_path,
            test_control_paths=test_control_paths,
            test_disease_paths=test_disease_paths,
        )
        return [(config, "validation")]

    step_cfg = (project.get_step_config("predictor") or {}).copy()
    if not step_cfg:
        legacy_validator = (project.get_step_config("validator") or {}).copy()
        if legacy_validator:
            warnings.warn(
                "step_config.validator is deprecated; use step_config.predictor instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            step_cfg = legacy_validator
    classifier_step = project.get_step_config("classifier") or {}
    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            step_cfg = {**step_cfg, **overrides}

    paths = project.get_derived_paths()
    base_path = project.samples_base_path

    if _predictor_blind_has_groups(step_cfg):
        if test_control_paths is not None or test_disease_paths is not None:
            raise ValueError(
                "Do not combine --test-control/--test-disease with step_config.predictor.blind."
            )
        _assert_predictor_blind_exclusive(step_cfg)
        mp = step_cfg.get("model_path") or classifier_step.get("save_classifier_path")
        md = step_cfg.get("model_dir")
        multiclass_path = _get_multiclass_model_path(project, step_cfg, paths)
        if mp:
            md = None
        elif md:
            mp = None
        elif multiclass_path is not None:
            mp = str(multiclass_path)
            md = None
        else:
            raise ValueError(
                "predictor.blind on a comparison project requires step_config.predictor.model_path, "
                "model_dir, multiclass-classifier.pkl under classifier_dir, or classifier.save_classifier_path."
            )
        out_blind = str(Path(project.get_project_root()) / "predictors" / "blind")
        blind_kwargs = _build_blind_predictor_dict(
            step_cfg=step_cfg,
            project=project,
            project_path=project_path,
            base_path=base_path,
            output_dir=out_blind,
            model_path=mp,
            model_dir=md,
            comparison_label="blind",
        )
        return [(PredictorConfig(**blind_kwargs), "blind")]

    # Prefer multiclass model when present: one config with test_group_paths
    multiclass_path = _get_multiclass_model_path(project, step_cfg, paths)
    if multiclass_path is not None:
        out_dir = str(Path(paths.validator_dir).resolve())
        cfg = _build_multiclass_predictor_config(
            project=project,
            step_cfg=step_cfg,
            paths=paths,
            base_path=base_path,
            project_path=project_path,
            out_dir=out_dir,
        )
        if test_control_paths is not None and test_disease_paths is not None:
            _apply_binary_cli_paths_to_multiclass_config(
                cfg,
                project,
                test_control_paths,
                test_disease_paths,
                base_path,
                project_path,
                project.path_remap,
            )
        return [(cfg, "multiclass")]

    controls_side = _effective_predictor_side(step_cfg, project, "controls")
    diseases_side = _effective_predictor_side(step_cfg, project, "diseases")
    ctrl_map = _expand_side_group_paths(controls_side, base_path, project_path, project.path_remap)
    dis_map = _expand_side_group_paths(diseases_side, base_path, project_path, project.path_remap)

    use_caller_test_paths = (
        test_control_paths is not None and test_disease_paths is not None
    )

    comparisons = project.get_comparisons()
    result: List[Tuple[PredictorConfig, str]] = []
    for spec in comparisons:
        comp_label = spec.comparison_label or spec.disease_group
        ctrl_label = spec.control_group
        dis_label = spec.disease_group
        classifier_output_dir = project.get_classifier_output_dir(ctrl_label, dis_label)
        detection_dir = project.get_detection_output_dir(ctrl_label, dis_label)
        project_name = project.project_name or "classifier"
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
            control_paths = [_resolve_one_path(p, base_path) for p in control_paths if p]
            disease_paths = [_resolve_one_path(p, base_path) for p in disease_paths if p]
            if project.path_remap:
                control_paths = _apply_path_remap(control_paths, project.path_remap)
                disease_paths = _apply_path_remap(disease_paths, project.path_remap)
            lineage: List[Dict[str, str]] = []
            for p in control_paths:
                lineage.append({"absolute_path": p, "side": "control", "group_label": "cli"})
            for p in disease_paths:
                lineage.append({"absolute_path": p, "side": "disease", "group_label": "cli"})
            rep_c = {"label": controls_side.get("label", ""), "groups": [{"label": "cli", "sample_paths": []}]}
            rep_d = {"label": diseases_side.get("label", ""), "groups": [{"label": "cli", "sample_paths": []}]}
        else:
            control_paths, lin_c = _collect_paths_and_lineage(
                "control", [ctrl_label], ctrl_map
            )
            disease_paths, lin_d = _collect_paths_and_lineage(
                "disease", [dis_label], dis_map
            )
            lineage = lin_c + lin_d
            rep_c = _filter_side_report(controls_side, [ctrl_label])
            rep_d = _filter_side_report(diseases_side, [dis_label])

        base: Dict[str, Any] = {
            "model_path": model_path,
            "model_dir": model_dir,
            "output_dir": out_dir,
            "test_control_paths": control_paths,
            "test_disease_paths": disease_paths,
            "path_remap": project.path_remap,
            "samples_base_path": project.samples_base_path,
            "debug": step_cfg.get("debug", False),
            "comparison_label": comp_label,
            "report_controls": rep_c,
            "report_diseases": rep_d,
            "sample_lineage": lineage,
            "panel": step_cfg.get("panel") if isinstance(step_cfg.get("panel"), dict) else None,
            "classifier_step_snapshot": _classifier_step_snapshot(classifier_step),
        }
        result.append((PredictorConfig(**base), comp_label))
    return result
