"""
Generate per-iteration project JSON and train/val CSVs for Monte Carlo runs.
"""

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _sample_name_from_path(full_path: str, base_path: str) -> str:
    """Return sample folder name (last component) for train CSV format."""
    p = Path(full_path)
    base = Path(base_path).resolve()
    try:
        p_resolved = p.resolve()
        if base in p_resolved.parents or p_resolved == base:
            return str(p_resolved.relative_to(base))
    except ValueError:
        pass
    return p.name


def write_train_csv(path: Path, full_paths: List[str], base_path: str) -> None:
    """Write a train CSV with header 'sample' and one column of sample names (resolvable with base_path)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    names = [_sample_name_from_path(p, base_path) for p in full_paths]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sample"])
        for n in names:
            w.writerow([n])


def write_val_csv(path: Path, full_paths: List[str]) -> None:
    """Write a validation CSV with header 'path' and one column of absolute paths for MethylPredictor."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path"])
        for p in full_paths:
            w.writerow([str(Path(p).resolve())])


def _first_control_and_disease_labels(base: Dict[str, Any]) -> tuple[str, str]:
    """Get first control group label and first disease group label from base project."""
    control_label = "healthy"
    disease_label = "disease"
    if "controls" in base and base["controls"] and base["controls"].get("groups"):
        control_label = base["controls"]["groups"][0].get("label", control_label)
    elif "control" in base and base["control"] and base["control"].get("groups"):
        control_label = base["control"]["groups"][0].get("label", control_label)
    if "diseases" in base and base["diseases"] and base["diseases"].get("groups"):
        disease_label = base["diseases"]["groups"][0].get("label", disease_label)
    elif "disease" in base and base["disease"] and base["disease"].get("groups"):
        disease_label = base["disease"]["groups"][0].get("label", disease_label)
    return control_label, disease_label


def _normalize_sample_paths(paths: List[str]) -> List[str]:
    seen = set()
    normalized: List[str] = []
    for path in paths:
        resolved = str(Path(path).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


def _build_centroid_step_override(
    previous_paths: Optional[List[str]],
    current_paths: List[str],
) -> Dict[str, Any]:
    prev = _normalize_sample_paths(previous_paths or [])
    curr = _normalize_sample_paths(current_paths)
    prev_set = set(prev)
    curr_set = set(curr)
    add_paths = [path for path in curr if path not in prev_set]
    remove_paths = [path for path in prev if path not in curr_set]
    return {
        "base_config": {
            "samples": prev,
            "add_samples": add_paths,
            "remove_samples": remove_paths,
        }
    }


def write_centroid_step_override(
    path: Path,
    previous_paths: Optional[List[str]],
    current_paths: List[str],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_centroid_step_override(previous_paths, current_paths)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def generate_run_project(
    base_project_path: str | Path,
    run_dir: Path,
    run_id: str,
    output_base: str,
    train_control_paths: List[str],
    train_disease_paths: List[str],
    val_control_paths: List[str],
    val_disease_paths: List[str],
    samples_base_path: str,
    previous_train_control_paths: Optional[List[str]] = None,
    previous_train_disease_paths: Optional[List[str]] = None,
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    """
    Load base project JSON, write train/val CSVs, and write the run's project.json.
    Overrides output_base, project_name, controls and diseases to single groups with train samples only.
    Called by methyl-validation with output_base = monte_carlo_runs_root (output_base/project_name/monte_carlo_runs)
    so the run's paths are monte_carlo_runs_root/run_id/centroids|detections|...

    Returns:
        (
            project_json_path,
            train_control_csv,
            train_disease_csv,
            val_control_csv,
            val_disease_csv,
            centroid_group1_override_json,
            centroid_group2_override_json,
        )
    """
    with open(base_project_path, encoding="utf-8") as f:
        base = json.load(f)

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    train_control_csv = run_dir / "train_control.csv"
    train_disease_csv = run_dir / "train_disease.csv"
    val_control_csv = run_dir / "val_control.csv"
    val_disease_csv = run_dir / "val_disease.csv"

    write_train_csv(train_control_csv, train_control_paths, samples_base_path)
    write_train_csv(train_disease_csv, train_disease_paths, samples_base_path)
    write_val_csv(val_control_csv, val_control_paths)
    write_val_csv(val_disease_csv, val_disease_paths)

    control_label, disease_label = _first_control_and_disease_labels(base)

    # Build project: same structure as pipeline expects (controls/diseases plural ok per pipeline normalizer)
    project = dict(base)
    project["output_base"] = output_base.rstrip("/")
    project["project_name"] = run_id
    project["samples_base_path"] = samples_base_path
    project["controls"] = {
        "label": control_label,
        "groups": [
            {"label": control_label, "sample_paths": [str(train_control_csv)]}
        ],
    }
    project["diseases"] = {
        "label": disease_label,
        "groups": [
            {"label": disease_label, "sample_paths": [str(train_disease_csv)]}
        ],
    }
    project["comparisons"] = [
        {"control_group": control_label, "disease_group": disease_label}
    ]

    project_path = run_dir / "project.json"
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)

    group1_override = write_centroid_step_override(
        run_dir / "centroid_group1_override.json",
        previous_train_control_paths,
        train_control_paths,
    )
    group2_override = write_centroid_step_override(
        run_dir / "centroid_group2_override.json",
        previous_train_disease_paths,
        train_disease_paths,
    )

    return (
        project_path,
        train_control_csv,
        train_disease_csv,
        val_control_csv,
        val_disease_csv,
        group1_override,
        group2_override,
    )


def _safe_cohort_filename_label(label: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", label.strip())
    return s or "cohort"


def infer_monte_carlo_layout(base_project_path: str | Path, n_cohorts: int) -> str:
    """
    Return ``\"binary\"`` for control/disease templates with exactly two MC cohorts (legacy).
    Return ``\"hierarchical_multiclass\"`` when the base project uses ``controls``/``diseases`` and
    the number of resolved centroid groups equals ``n_cohorts`` and ``n_cohorts`` ≥ 3.
    Return ``\"multiclass\"`` when the base project uses flat ``groups`` whose length matches ``n_cohorts``.
    """
    with open(base_project_path, encoding="utf-8") as f:
        raw = json.load(f)
    groups = raw.get("groups")
    if isinstance(groups, list) and len(groups) >= 2:
        if len(groups) != n_cohorts:
            raise ValueError(
                f"Base project flat groups count ({len(groups)}) must match Monte Carlo cohorts ({n_cohorts})."
            )
        return "multiclass"
    try:
        from methyl_utils import load_project

        proj = load_project(base_project_path)
        if proj.uses_control_disease():
            resolved = proj.get_resolved_groups()
            if n_cohorts >= 3 and len(resolved) == n_cohorts:
                return "hierarchical_multiclass"
    except Exception:
        pass
    if n_cohorts != 2:
        raise ValueError(
            "For control/disease projects: use exactly two Monte Carlo cohorts (binary), or "
            "K cohorts matching K resolved groups (multiclass hierarchical, K>=3), "
            "or a flat ``groups`` base project."
        )
    return "binary"


def _assert_flat_multiclass_template(base: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ensure base JSON is a flat ``groups`` template (no control/disease). Return groups list."""
    for key in ("control", "disease", "controls", "diseases"):
        if base.get(key) is not None:
            raise ValueError(
                "Multiclass Monte Carlo requires a base project with top-level ``groups`` only "
                f"(found {key!r}). For two-cohort control/disease templates, use the binary validation path."
            )
    groups = base.get("groups")
    if not isinstance(groups, list) or len(groups) < 2:
        raise ValueError("Multiclass Monte Carlo base project must define at least two top-level ``groups``.")
    return groups


def generate_run_project_multiclass(
    base_project_path: str | Path,
    run_dir: Path,
    run_id: str,
    output_base: str,
    train_by_label: Dict[str, List[str]],
    val_by_label: Dict[str, List[str]],
    cohort_labels: List[str],
    samples_base_path: str,
) -> Tuple[Path, Path]:
    """
    Write per-cohort train CSVs, validation JSON for ``methyl-predictor --test-groups``,
    and a run ``project.json`` with flat ``groups`` sample_paths pointing at train CSVs only.

    ``cohort_labels`` order must match ``base`` template ``groups[i].label``.
    """
    with open(base_project_path, encoding="utf-8") as f:
        base = json.load(f)

    groups_template = _assert_flat_multiclass_template(base)
    if len(groups_template) != len(cohort_labels):
        raise ValueError(
            f"Base project has {len(groups_template)} groups but Monte Carlo config has "
            f"{len(cohort_labels)} cohorts; counts must match."
        )
    for i, lbl in enumerate(cohort_labels):
        gl = groups_template[i].get("label")
        if gl != lbl:
            raise ValueError(
                f"Monte Carlo cohorts[{i}].label {lbl!r} != base project groups[{i}].label {gl!r}."
            )

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    train_csv_by_label: Dict[str, Path] = {}
    for lbl in cohort_labels:
        if lbl not in train_by_label or lbl not in val_by_label:
            raise ValueError(f"Missing train/val paths for cohort label {lbl!r}")
        safe = _safe_cohort_filename_label(lbl)
        p = run_dir / f"train_{safe}.csv"
        write_train_csv(p, train_by_label[lbl], samples_base_path)
        train_csv_by_label[lbl] = p

    val_payload: List[Dict[str, Any]] = []
    for lbl in cohort_labels:
        val_payload.append(
            {
                "label": lbl,
                "paths": [str(Path(p).resolve()) for p in val_by_label[lbl]],
            }
        )
    val_groups_json = run_dir / "val_test_groups.json"
    val_groups_json.parent.mkdir(parents=True, exist_ok=True)
    with open(val_groups_json, "w", encoding="utf-8") as f:
        json.dump(val_payload, f, indent=2)

    project = dict(base)
    project["output_base"] = output_base.rstrip("/")
    project["project_name"] = run_id
    project["samples_base_path"] = samples_base_path
    new_groups: List[Dict[str, Any]] = []
    for i, g in enumerate(groups_template):
        if not isinstance(g, dict):
            raise ValueError(f"groups[{i}] must be an object")
        gg = dict(g)
        lbl = cohort_labels[i]
        gg["sample_paths"] = [str(train_csv_by_label[lbl].resolve())]
        new_groups.append(gg)
    project["groups"] = new_groups

    project_path = run_dir / "project.json"
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)

    return project_path, val_groups_json


def _patch_side_groups_for_mc(
    groups: Any,
    train_csv_by_label: Dict[str, Path],
) -> List[Dict[str, Any]]:
    """Replace sample_paths with per-run train CSVs; supports disease ``stages`` (leaf = parent_child)."""
    if not isinstance(groups, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in groups:
        if not isinstance(item, dict):
            continue
        if item.get("stages"):
            parent = dict(item)
            new_stages: List[Dict[str, Any]] = []
            for st in item.get("stages") or []:
                if not isinstance(st, dict) or not st.get("label"):
                    continue
                plab = str(item.get("label", ""))
                leaf = f"{plab}_{st['label']}"
                if leaf not in train_csv_by_label:
                    raise ValueError(
                        f"Monte Carlo train CSV missing for disease leaf {leaf!r} "
                        f"(expected cohort label in config)."
                    )
                s2 = dict(st)
                s2["sample_paths"] = [str(train_csv_by_label[leaf].resolve())]
                new_stages.append(s2)
            parent["stages"] = new_stages
            out.append(parent)
        else:
            g2 = dict(item)
            lab = str(g2.get("label", ""))
            if lab not in train_csv_by_label:
                raise ValueError(f"Monte Carlo train CSV missing for group label {lab!r}")
            g2["sample_paths"] = [str(train_csv_by_label[lab].resolve())]
            out.append(g2)
    return out


def generate_run_project_hierarchical_multiclass(
    base_project_path: str | Path,
    run_dir: Path,
    run_id: str,
    output_base: str,
    train_by_label: Dict[str, List[str]],
    val_by_label: Dict[str, List[str]],
    cohort_labels: List[str],
    samples_base_path: str,
) -> Tuple[Path, Path]:
    """
    Same outputs as ``generate_run_project_multiclass`` but keeps ``controls`` / ``diseases``
    (and optional nested ``stages``) in ``project.json`` for full centroid/detector layout.
    """
    from methyl_utils import load_project

    proj = load_project(base_project_path)
    resolved_order = [x[0] for x in proj.get_resolved_groups()]
    if list(cohort_labels) != list(resolved_order):
        raise ValueError(
            "Monte Carlo cohorts order and labels must match project resolved groups "
            f"(expected {resolved_order!r}, got {list(cohort_labels)!r})."
        )

    with open(base_project_path, encoding="utf-8") as f:
        base = json.load(f)

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    train_csv_by_label: Dict[str, Path] = {}
    for lbl in cohort_labels:
        if lbl not in train_by_label or lbl not in val_by_label:
            raise ValueError(f"Missing train/val paths for cohort label {lbl!r}")
        safe = _safe_cohort_filename_label(lbl)
        p = run_dir / f"train_{safe}.csv"
        write_train_csv(p, train_by_label[lbl], samples_base_path)
        train_csv_by_label[lbl] = p

    val_payload: List[Dict[str, Any]] = []
    for lbl in cohort_labels:
        val_payload.append(
            {
                "label": lbl,
                "paths": [str(Path(p).resolve()) for p in val_by_label[lbl]],
            }
        )
    val_groups_json = run_dir / "val_test_groups.json"
    val_groups_json.parent.mkdir(parents=True, exist_ok=True)
    with open(val_groups_json, "w", encoding="utf-8") as f:
        json.dump(val_payload, f, indent=2)

    project = dict(base)
    project["output_base"] = output_base.rstrip("/")
    project["project_name"] = run_id
    project["samples_base_path"] = samples_base_path

    for key in ("controls", "control"):
        side = project.get(key)
        if isinstance(side, dict) and side.get("groups"):
            side = dict(side)
            side["groups"] = _patch_side_groups_for_mc(side["groups"], train_csv_by_label)
            project[key] = side
    for key in ("diseases", "disease"):
        side = project.get(key)
        if isinstance(side, dict) and side.get("groups"):
            side = dict(side)
            side["groups"] = _patch_side_groups_for_mc(side["groups"], train_csv_by_label)
            project[key] = side

    project_path = run_dir / "project.json"
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)

    return project_path, val_groups_json
