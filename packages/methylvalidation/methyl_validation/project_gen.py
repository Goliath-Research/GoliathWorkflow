"""
Generate per-iteration project JSON and train/val CSVs for Monte Carlo runs.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List


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
    """Write a validation CSV with header 'path' and one column of full paths for MethylValidator."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path"])
        for p in full_paths:
            w.writerow([p])


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
) -> tuple[Path, Path, Path, Path, Path]:
    """
    Load base project JSON, write train/val CSVs, and write the run's project.json.
    Overrides output_base, project_name, controls and diseases to single groups with train samples only.
    Called by methyl-validation with output_base = monte_carlo_runs_root (output_base/project_name/monte_carlo_runs)
    so the run's paths are monte_carlo_runs_root/run_id/centroids|detections|...

    Returns:
        (project_json_path, train_control_csv, train_disease_csv, val_control_csv, val_disease_csv)
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

    return project_path, train_control_csv, train_disease_csv, val_control_csv, val_disease_csv
