"""
True held-out batch evaluation (Workflow 3).

Score a *frozen* production model on a designated hold-out partition (sample
batches that were never used for training or model selection) and report the
bootstrap distribution of QC metrics (balanced accuracy, sensitivity,
specificity, F1, ROC-AUC).

Unlike ``--predictor-only`` (Workflow 2), which draws random holdouts from the
development pool that overlap the training centroid, this workflow evaluates a
fixed, disjoint batch. Disjointness is enforced two ways:

1. ``validation_partitions`` already validates non-overlap of the hold-out role
   with ``development_train`` at config-parse time.
2. :func:`apply_holdout_exclusion_to_project_dict` filters the hold-out samples
   out of the production cohort list files at ``--freeze`` time, and
   :func:`run_holdout_evaluation` preflights that a ``holdout_manifest.json``
   recorded that exclusion before trusting the held-out claim.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .cohort_inference import infer_monte_carlo_cohorts_from_project
from .split import load_and_resolve_sample_paths

HOLDOUT_MANIFEST_NAME = "holdout_manifest.json"


def _basename(p: str) -> str:
    return Path(str(p)).name


def _samples_base_path(project_dict: Dict[str, Any]) -> str:
    return str(project_dict.get("samples_base_path") or ".")


def _control_disease_group_csvs(project_dict: Dict[str, Any]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Return (control_groups, disease_groups) as [{label, csv}] using cohort inference sides."""
    controls = project_dict.get("controls") or project_dict.get("control") or {}
    diseases = project_dict.get("diseases") or project_dict.get("disease") or {}
    ctrl_dict = {"controls": controls} if controls else {}
    dis_dict = {"diseases": diseases} if diseases else {}
    control_groups = infer_monte_carlo_cohorts_from_project(ctrl_dict, Path(".")) if controls else []
    disease_groups = infer_monte_carlo_cohorts_from_project(dis_dict, Path(".")) if diseases else []
    # Flat "groups" layout: treat control-side by heuristic label match.
    if not control_groups and not disease_groups:
        flat = infer_monte_carlo_cohorts_from_project(project_dict, Path("."))
        for g in flat:
            label = g["label"].strip().lower()
            if any(tok in label for tok in ("healthy", "control", "normal", "all")):
                control_groups.append(g)
            else:
                disease_groups.append(g)
    return control_groups, disease_groups


def _group_label_to_basenames(
    groups: Sequence[Dict[str, str]],
    base_path: str,
) -> Dict[str, set[str]]:
    out: Dict[str, set[str]] = {}
    for g in groups:
        csv_path = g.get("csv")
        if not csv_path:
            continue
        try:
            paths = load_and_resolve_sample_paths(csv_path, base_path)
        except FileNotFoundError:
            continue
        out[g["label"]] = {_basename(p) for p in paths}
    return out


def resolve_holdout_groups(
    project_dict: Dict[str, Any],
    holdout_paths: Sequence[str],
) -> Dict[str, Any]:
    """
    Classify hold-out sample paths into project class groups by basename membership.

    Returns a dict with:
      - ``binary``: bool (True when exactly one control side and one disease side apply),
      - ``control_paths`` / ``disease_paths``: absolute paths (binary layout),
      - ``groups_by_label``: {label: [abs_path]} (multiclass layout),
      - ``unresolved``: hold-out basenames not found in any project cohort.
    """
    base_path = _samples_base_path(project_dict)
    control_groups, disease_groups = _control_disease_group_csvs(project_dict)
    ctrl_members = _group_label_to_basenames(control_groups, base_path)
    dis_members = _group_label_to_basenames(disease_groups, base_path)

    control_basenames: set[str] = set().union(*ctrl_members.values()) if ctrl_members else set()
    label_by_basename: Dict[str, str] = {}
    for label, names in {**ctrl_members, **dis_members}.items():
        for nm in names:
            label_by_basename.setdefault(nm, label)

    control_paths: List[str] = []
    disease_paths: List[str] = []
    groups_by_label: Dict[str, List[str]] = {}
    unresolved: List[str] = []
    for raw in holdout_paths:
        abs_path = str(Path(raw)) if Path(raw).is_absolute() else str(Path(base_path).resolve() / raw)
        bn = _basename(raw)
        label = label_by_basename.get(bn)
        if label is None:
            unresolved.append(bn)
            continue
        groups_by_label.setdefault(label, []).append(abs_path)
        if bn in control_basenames:
            control_paths.append(abs_path)
        else:
            disease_paths.append(abs_path)

    n_control_groups = len({lbl for lbl in groups_by_label if lbl in ctrl_members})
    n_disease_groups = len({lbl for lbl in groups_by_label if lbl in dis_members})
    binary = (n_control_groups <= 1) and (n_disease_groups <= 1) and (len(groups_by_label) <= 2)

    return {
        "binary": binary,
        "control_paths": control_paths,
        "disease_paths": disease_paths,
        "groups_by_label": groups_by_label,
        "unresolved": unresolved,
    }


def apply_holdout_exclusion_to_project_dict(
    project_dict: Dict[str, Any],
    holdout_basenames: set[str],
    out_dir: Path,
) -> List[str]:
    """
    Rewrite each cohort list file referenced by ``project_dict`` to drop hold-out
    samples, writing filtered CSVs under ``out_dir`` and repointing the project.

    Returns the sorted list of excluded sample basenames actually removed. This is
    what makes the production model train on a set disjoint from the hold-out batch.
    """
    if not holdout_basenames:
        return []
    filtered_dir = Path(out_dir) / "holdout_filtered_cohorts"
    filtered_dir.mkdir(parents=True, exist_ok=True)
    removed: set[str] = set()

    def _filter_group(group: Dict[str, Any], scope: str, gid: str) -> None:
        paths = group.get("sample_paths")
        if not isinstance(paths, list) or not paths:
            return
        src_csv = Path(str(paths[0]))
        if not src_csv.is_file():
            return
        kept_rows: List[List[str]] = []
        header: Optional[List[str]] = None
        with open(src_csv, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            first = next(reader, None)
            has_header = bool(
                first and first[0].strip().lower() in ("sample", "path", "sample_path", "name", "id")
            )
            if has_header:
                header = first
            elif first and first[0].strip():
                if _basename(first[0]) in holdout_basenames:
                    removed.add(_basename(first[0]))
                else:
                    kept_rows.append(first)
            for row in reader:
                if not row or not row[0].strip():
                    continue
                if _basename(row[0]) in holdout_basenames:
                    removed.add(_basename(row[0]))
                else:
                    kept_rows.append(row)
        dst_csv = filtered_dir / f"{scope}_{gid}_{src_csv.name}"
        with open(dst_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if header is not None:
                writer.writerow(header)
            writer.writerows(kept_rows)
        group["sample_paths"] = [str(dst_csv)]

    def _walk_side(side_key: str) -> None:
        side = project_dict.get(side_key)
        if not isinstance(side, dict):
            return
        groups = side.get("groups")
        if not isinstance(groups, list):
            return
        for gi, g in enumerate(groups):
            if not isinstance(g, dict):
                continue
            stages = g.get("stages")
            if isinstance(stages, list) and stages:
                for si, st in enumerate(stages):
                    if isinstance(st, dict):
                        _filter_group(st, side_key, f"{gi}_{si}")
            else:
                _filter_group(g, side_key, str(gi))

    for side_key in ("controls", "control", "diseases", "disease"):
        _walk_side(side_key)
    flat_groups = project_dict.get("groups")
    if isinstance(flat_groups, list):
        for gi, g in enumerate(flat_groups):
            if isinstance(g, dict):
                _filter_group(g, "groups", str(gi))

    return sorted(removed)


def write_holdout_manifest(out_dir: Path, *, partition: str, holdout_paths: Sequence[str], excluded: Sequence[str]) -> Path:
    """Record which samples were held out and excluded from production training."""
    manifest = {
        "partition": str(partition),
        "holdout_samples": sorted({_basename(p) for p in holdout_paths}),
        "excluded_from_training": sorted(set(excluded)),
        "n_holdout": len({_basename(p) for p in holdout_paths}),
        "n_excluded_from_training": len(set(excluded)),
    }
    path = Path(out_dir) / HOLDOUT_MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path


def read_predictions_for_bootstrap(predictions_csv: Path) -> Dict[str, Any]:
    """
    Read a MethylPredictor ``predictions.csv`` into arrays for the bootstrap.

    Requires ``expected_class`` (true labels) and ``prediction`` columns; probability
    columns ``prob_class{i}`` are used for AUC when present.
    """
    import pandas as pd

    df = pd.read_csv(predictions_csv)
    if "expected_class" not in df.columns or "prediction" not in df.columns:
        raise ValueError(
            f"{predictions_csv} must contain 'expected_class' and 'prediction' columns for labeled hold-out evaluation."
        )
    y_true = df["expected_class"].to_numpy(dtype=int)
    y_pred = df["prediction"].to_numpy(dtype=int)
    prob_cols = [c for c in df.columns if c.startswith("prob_class")]

    def _col_index(c: str) -> int:
        try:
            return int(c.replace("prob_class", ""))
        except ValueError:
            return 1_000_000

    prob_cols = sorted(prob_cols, key=_col_index)
    y_proba = df[prob_cols].to_numpy(dtype=float) if prob_cols else None
    return {"y_true": y_true, "y_pred": y_pred, "y_proba": y_proba, "n_rows": int(len(df))}


def load_class_roles_from_metrics(metrics_json: Path) -> Dict[str, Any]:
    """Read control/disease class indices + class names from validation_metrics.json when available."""
    try:
        with open(metrics_json, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    roles = data.get("class_roles") or {}
    return {
        "control_index": int(roles.get("control_class_index", 0)) if roles else 0,
        "disease_indices": [int(i) for i in roles.get("disease_class_indices", [])] if roles else [],
        "n_classes": int(data.get("n_classes", 0)) or None,
        "class_names": data.get("class_names"),
    }


def _preflight_exclusion(
    manifest_path: Path,
    holdout_basenames: set[str],
) -> Tuple[bool, str]:
    """Verify the frozen model recorded exclusion of all current hold-out samples."""
    if not manifest_path.is_file():
        return False, (
            f"No {HOLDOUT_MANIFEST_NAME} next to the frozen project ({manifest_path}). "
            "Re-run '--freeze' after populating validation_partitions so hold-out samples are "
            "excluded from production training, or set holdout_exclude_from_training=false to "
            "evaluate without the disjointness guarantee."
        )
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Could not read {manifest_path}: {exc}"
    excluded = {str(x) for x in manifest.get("excluded_from_training", [])}
    missing = sorted(holdout_basenames - excluded)
    if missing:
        preview = missing[:8]
        more = f" (+{len(missing) - len(preview)} more)" if len(missing) > len(preview) else ""
        return False, (
            "Hold-out samples were NOT excluded from the frozen model's training set: "
            f"{preview}{more}. Re-run '--freeze' with these samples in the "
            "validation_partitions hold-out role."
        )
    return True, "ok"


def run_holdout_evaluation(
    config: Any,
    frozen_project_path: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    """
    End-to-end held-out batch evaluation against a frozen model.

    Steps: resolve hold-out partition by class -> (preflight disjointness) -> run
    methyl-predictor once on the frozen model -> bootstrap QC-metric distributions
    -> write artifacts under ``output_dir``.
    """
    from .holdout_bootstrap import bootstrap_holdout_metrics
    from .pipeline_runner import run_predictor, run_predictor_multiclass
    from .project_gen import write_val_csv
    from .validator_metrics import write_metrics_distribution_plotly

    frozen_project_path = Path(frozen_project_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(frozen_project_path, encoding="utf-8") as f:
        project_dict = json.load(f)

    partition = str(getattr(config, "holdout_partition", "locked_test"))
    partitions = getattr(config, "validation_partitions", None)
    holdout_paths: List[str] = list(getattr(partitions, partition, []) or []) if partitions is not None else []
    if not holdout_paths:
        raise ValueError(
            f"No hold-out samples in validation_partitions.{partition}. Populate that partition "
            "in the profile/project actionConfig.validation before running --holdout-eval."
        )
    holdout_basenames = {_basename(p) for p in holdout_paths}

    if bool(getattr(config, "holdout_exclude_from_training", True)):
        ok, msg = _preflight_exclusion(
            frozen_project_path.parent / HOLDOUT_MANIFEST_NAME, holdout_basenames
        )
        if not ok:
            raise ValueError(msg)

    resolved = resolve_holdout_groups(project_dict, holdout_paths)
    if resolved["unresolved"]:
        preview = resolved["unresolved"][:8]
        raise ValueError(
            "Hold-out samples not found in any project cohort (cannot assign a class label): "
            f"{preview}. Add them to the appropriate control/disease cohort with target labels."
        )

    pred_out = output_dir / "predictor"
    pred_out.mkdir(parents=True, exist_ok=True)

    if resolved["binary"]:
        ctrl_csv = output_dir / "holdout_control.csv"
        dis_csv = output_dir / "holdout_disease.csv"
        write_val_csv(ctrl_csv, resolved["control_paths"])
        write_val_csv(dis_csv, resolved["disease_paths"])
        rc, out, err = run_predictor(frozen_project_path, ctrl_csv, dis_csv, pred_out)
    else:
        groups = [{"label": lbl, "paths": paths} for lbl, paths in resolved["groups_by_label"].items()]
        test_groups_json = output_dir / "holdout_test_groups.json"
        with open(test_groups_json, "w", encoding="utf-8") as f:
            json.dump(groups, f, indent=2)
        rc, out, err = run_predictor_multiclass(frozen_project_path, test_groups_json, pred_out)

    if rc != 0:
        (output_dir / "predictor_stderr.log").write_text(err or "", encoding="utf-8")
        raise RuntimeError(f"methyl-predictor failed on hold-out batch (exit {rc}). See {output_dir/'predictor_stderr.log'}")

    predictions_csv = pred_out / "predictions.csv"
    if not predictions_csv.is_file():
        raise RuntimeError(f"Predictor did not produce {predictions_csv}")
    arrays = read_predictions_for_bootstrap(predictions_csv)
    roles = load_class_roles_from_metrics(pred_out / "validation_metrics.json")

    n_classes = roles.get("n_classes")
    control_index = int(roles.get("control_index", 0))
    disease_indices = roles.get("disease_indices") or None

    result = bootstrap_holdout_metrics(
        arrays["y_true"],
        arrays["y_pred"],
        arrays["y_proba"],
        n_classes=n_classes,
        control_index=control_index,
        disease_indices=disease_indices,
        n_bootstrap=int(getattr(config, "holdout_n_bootstrap", 1000)),
        ci=float(getattr(config, "holdout_ci", 0.95)),
        seed=getattr(config, "holdout_seed", None),
        stratified=bool(getattr(config, "holdout_stratified", True)),
    )
    result["partition"] = partition
    result["frozen_project"] = str(frozen_project_path)
    result["predictions_csv"] = str(predictions_csv)
    result["class_names"] = roles.get("class_names")

    bootstrap_json = output_dir / "holdout_metrics_bootstrap.json"
    serializable = {k: v for k, v in result.items() if k != "samples"}
    with open(bootstrap_json, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)

    import pandas as pd

    dist_df = pd.DataFrame(result["samples"])
    dist_csv = output_dir / "holdout_metrics_distribution.csv"
    dist_df.to_csv(dist_csv, index=False)
    try:
        write_metrics_distribution_plotly(dist_df, output_dir / "holdout_metrics_distribution.html")
    except Exception:
        pass

    result["outputs"] = {
        "bootstrap_json": str(bootstrap_json),
        "distribution_csv": str(dist_csv),
        "predictor_dir": str(pred_out),
    }
    return result
