from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from methyl_validation.cli import _write_detector_featurecuts_override
from methyl_validation.cli import _count_run_samples_from_existing_files
from methyl_validation.config import MonteCarloConfig
from methyl_validation.stability import load_discovery_dmps


def _minimal_mc_dict(**extra):
    return {
        "samples_base_path": "/tmp/s",
        "healthy_csv": "h.csv",
        "disease_csv": "d.csv",
        "train_fraction": 0.8,
        "n_iterations": 1,
        "base_project": "p.json",
        "output_base": "/tmp/out",
        **extra,
    }


def test_write_detector_featurecuts_override(tmp_path: Path):
    cfg = MonteCarloConfig.model_validate(
        _minimal_mc_dict(
            stability_featurecuts_enabled=True,
            stability_target_balanced_accuracy=0.95,
            stability_min_selected_dmps=1200,
        )
    )
    out = _write_detector_featurecuts_override(tmp_path / "run_0001", cfg)
    assert out is not None and out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["classifier_dmp_selection"] == "featurecuts_validation"
    assert payload["target_balanced_accuracy"] == 0.95
    assert payload["min_selected_dmps"] == 1200


def test_load_discovery_dmps_prefers_classifier_panel(tmp_path: Path):
    det = tmp_path / "run_0001" / "detections" / "healthy" / "pca"
    det.mkdir(parents=True)
    pd.DataFrame(
        {"chromosome": ["1", "1"], "position": [100, 200], "context": ["CG", "CG"]}
    ).to_csv(det / "dmps-1-discovery.csv", index=False)
    pd.DataFrame(
        {"chromosome": ["1"], "position": [100], "context": ["CG"]}
    ).to_csv(det / "dmps-1-classifier.csv", index=False)

    df_classifier = load_discovery_dmps(tmp_path / "run_0001", prefer_classifier_panel=True)
    assert df_classifier is not None
    assert len(df_classifier) == 1

    df_discovery = load_discovery_dmps(tmp_path / "run_0001", prefer_classifier_panel=False)
    assert df_discovery is not None
    assert len(df_discovery) == 2


def test_count_run_samples_from_existing_files(tmp_path: Path):
    run_dir = tmp_path / "run_0001"
    run_dir.mkdir(parents=True)
    (run_dir / "train_control.csv").write_text("sample\nA\nB\n", encoding="utf-8")
    (run_dir / "train_disease.csv").write_text("sample\nC\n", encoding="utf-8")
    (run_dir / "val_control.csv").write_text("path\n/x/A\n", encoding="utf-8")
    (run_dir / "val_disease.csv").write_text("path\n/x/C\n/x/D\n", encoding="utf-8")
    n_train, n_val = _count_run_samples_from_existing_files(run_dir)
    assert n_train == 3
    assert n_val == 3
