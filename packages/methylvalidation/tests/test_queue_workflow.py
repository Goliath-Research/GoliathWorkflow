"""Queue plan / export (no full pipeline)."""

from __future__ import annotations

import json
from pathlib import Path

from methyl_validation.queue_export import export_queue_artifacts


def _binary_project_for_mc(tmp_path: Path) -> Path:
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\nH2\nH3\nH4\nH5\n", encoding="utf-8")
    d.write_text("sample\nD1\nD2\nD3\nD4\nD5\n", encoding="utf-8")
    p = tmp_path / "project.json"
    p.write_text(
        json.dumps(
            {
                "project_name": "qtest",
                "output_base": str(tmp_path / "out"),
                "samples_base_path": str(tmp_path),
                "groups": [
                    {"label": "healthy", "sample_paths": [str(h)]},
                    {"label": "disease", "sample_paths": [str(d)]},
                ],
                "step_config": {
                    "validation": {
                        "train_fraction": 0.6,
                        "n_iterations": 2,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return p


def test_export_queue_from_plan(tmp_path: Path) -> None:
    from methyl_validation.mc_config_load import (
        apply_monte_carlo_config_overrides,
        ensure_monte_carlo_output_tree,
        load_monte_carlo_config,
    )
    from methyl_validation.planner import plan_discovery_runs
    from argparse import Namespace

    project = _binary_project_for_mc(tmp_path)
    args = Namespace(
        project=project,
        config=None,
        iterations=None,
        seed=42,
        output_base=None,
        samples_base_path=None,
        path_remap=None,
        stability=None,
        stability_featurecuts=None,
        stability_target_ba=None,
        stability_min_selected_dmps=None,
        skip_enricher=None,
        predictor_only=None,
        model_backend=None,
        post_model_backend=None,
        covariates_path=None,
        tabular_max_dmps=None,
        tabular_model_type=None,
        tabular_methods_json=None,
        tabular_save_train_dataset=None,
        tabular_train_dataset_path=None,
        generative_latent_dim=None,
        generative_kl_weight=None,
        generative_density_type=None,
        generative_epochs=None,
        generative_batch_size=None,
        generative_seed=None,
        generative_calibrate=None,
        no_generative_covariates_strict=None,
    )
    config, _ = load_monte_carlo_config(args, None)
    config = apply_monte_carlo_config_overrides(config, args)
    base, _bc, _ob, mcr = ensure_monte_carlo_output_tree(config)
    plan_discovery_runs(
        config=config, base_project=base, monte_carlo_runs_root=mcr, overwrite=False
    )
    summ = export_queue_artifacts(mcr)
    assert summ["n_tasks"] == 2
    man = mcr / "queue" / "queue_manifest.jsonl"
    assert man.is_file()
    line = man.read_text(encoding="utf-8").strip().splitlines()[0]
    rec = json.loads(line)
    assert "methyl-validation" in rec["command"]
    assert rec["command"][1] == "run-task"


def test_plan_runs_idempotent_replan_same_seed(tmp_path: Path) -> None:
    import shutil

    from argparse import Namespace

    from methyl_validation.mc_config_load import (
        apply_monte_carlo_config_overrides,
        ensure_monte_carlo_output_tree,
        load_monte_carlo_config,
    )
    from methyl_validation.planner import plan_discovery_runs

    project = _binary_project_for_mc(tmp_path)
    ns = dict(
        project=project,
        config=None,
        seed=99,
        path_remap=None,
        stability=None,
        stability_featurecuts=None,
        stability_target_ba=None,
        stability_min_selected_dmps=None,
        skip_enricher=None,
        predictor_only=None,
        model_backend=None,
        post_model_backend=None,
        covariates_path=None,
        tabular_max_dmps=None,
        tabular_model_type=None,
        tabular_methods_json=None,
        tabular_save_train_dataset=None,
        tabular_train_dataset_path=None,
        generative_latent_dim=None,
        generative_kl_weight=None,
        generative_density_type=None,
        generative_epochs=None,
        generative_batch_size=None,
        generative_seed=None,
        generative_calibrate=None,
        no_generative_covariates_strict=None,
        iterations=None,
        output_base=None,
        samples_base_path=None,
    )
    args = Namespace(**ns)
    config, _ = load_monte_carlo_config(args, None)
    config = apply_monte_carlo_config_overrides(config, args)
    _, _, _, mcr = ensure_monte_carlo_output_tree(config)
    if mcr.is_dir():
        shutil.rmtree(mcr)
    plan_discovery_runs(
        config=config,
        base_project=Path(config.base_project),
        monte_carlo_runs_root=mcr,
        overwrite=True,
    )
    p1 = (mcr / "run_0001" / "project.json").read_text()
    shutil.rmtree(mcr)
    plan_discovery_runs(
        config=config,
        base_project=Path(config.base_project),
        monte_carlo_runs_root=mcr,
        overwrite=True,
    )
    p2 = (mcr / "run_0001" / "project.json").read_text()
    assert p1 == p2
