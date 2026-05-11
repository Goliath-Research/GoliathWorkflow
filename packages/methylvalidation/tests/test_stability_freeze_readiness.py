"""Tests for stability_freeze_readiness analyzer."""

import json
from pathlib import Path

import pandas as pd

from methyl_validation.stability_freeze_readiness import (
    analyze_project_root,
    render_markdown,
)


def _write_minimal_project(tree: Path) -> None:
    mc = tree / "monte_carlo_runs"
    stab = mc / "stability"
    prod = mc / "production"
    prog = prod / "progression"
    stab.mkdir(parents=True)
    prod.mkdir(parents=True)
    prog.mkdir(parents=True)

    stability_summary = {
        "dmp_stability": {
            "n_runs_analyzed": 10,
            "skipped_no_discovery": 0,
            "skipped_low_balanced_accuracy": 0,
            "min_balanced_accuracy": None,
            "total_unique_dmps": 1000,
            "stable_dmps_at_threshold": 2,
            "min_frequency": 0.8,
            "stable_dmp_fraction": 0.002,
        }
    }
    (stab / "stability_summary.json").write_text(json.dumps(stability_summary), encoding="utf-8")
    pd.DataFrame(
        {
            "chromosome": ["1", "1"],
            "position": [100, 200],
            "frequency": [1.0, 1.0],
            "count": [10, 10],
            "n_runs": [10, 10],
            "effect_size": [0.5, 0.4],
            "p_value": [0.01, 0.02],
            "q_value": [0.05, 0.06],
        }
    ).to_csv(stab / "stable_dmps_production.csv", index=False)

    production_summary = {
        "success": True,
        "errors": [],
        "timings": [
            {"step_name": "methyl-detector", "duration_seconds": 1.0, "return_code": 0},
        ],
        "fixed_dmp_panel": str(prod / "stable_dmps_genomewide.csv"),
        "production_project": str(prod / "project.json"),
    }
    (prod / "production_summary.json").write_text(json.dumps(production_summary), encoding="utf-8")

    project = {
        "project_name": "production",
        "step_config": {
            "detection": {
                "fixed_dmp_panel": str(prod / "stable_dmps_genomewide.csv"),
                "alpha": 0.05,
            }
        },
    }
    (prod / "project.json").write_text(json.dumps(project), encoding="utf-8")
    pd.DataFrame({"chromosome": ["1", "1"], "position": [100, 200]}).to_csv(
        prod / "stable_dmps_genomewide.csv", index=False
    )

    progression_summary = {
        "ordered_comparison_labels": ["g1", "g2", "g3", "g4"],
        "missing_inputs": [],
        "genes_rows": 10,
        "pathways_rows": 20,
        "modules_rows": 8,
        "modules_long_csv": str(prog / "modules_long.csv"),
    }
    (prog / "summary.json").write_text(json.dumps(progression_summary), encoding="utf-8")

    # Slim progression schema (stage_index + comparison + module + score)
    rows = []
    for si, comp in enumerate(["g1", "g2", "g3", "g4"]):
        rows.append(
            {"stage_index": si, "comparison": comp, "rank": 1, "score": 0.1 * (si + 1), "module": "ModA"}
        )
        rows.append(
            {"stage_index": si, "comparison": comp, "rank": 2, "score": 0.5, "module": "ModB"}
        )
    pd.DataFrame(rows).to_csv(prog / "modules_long.csv", index=False)
    pd.DataFrame(
        {
            "entity_type": ["module"],
            "entity_id": ["ModA"],
            "entity_label": ["ModA"],
            "stages_present": ["0,1,2,3"],
            "n_stages_present": [4],
            "progression_labels": ["monotonic_up"],
        }
    ).to_csv(prog / "entities_progression_labels.csv", index=False)


def test_analyze_and_render_go(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    report = analyze_project_root(root)
    assert report["verdict"]["overall"] in ("go", "go_with_risks")
    assert report["verdict"]["stability"] == "pass"
    assert report["verdict"]["freeze"] == "pass"
    md = render_markdown(report)
    assert "Stability and freeze readiness report" in md
    assert "ModA" in md or "module" in md.lower()


def test_no_go_on_legacy_detector_keys(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    prod = root / "monte_carlo_runs" / "production"
    proj = json.loads((prod / "project.json").read_text(encoding="utf-8"))
    proj["step_config"]["detection"]["max_dmps_for_classifier"] = 10000
    (prod / "project.json").write_text(json.dumps(proj), encoding="utf-8")
    report = analyze_project_root(root)
    assert report["verdict"]["freeze"] == "fail"
    assert report["verdict"]["overall"] == "no_go"
