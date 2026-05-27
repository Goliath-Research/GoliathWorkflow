from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from methyl_validation import cli
from methyl_validation.cli import (
    _deep_merge_dicts,
    _list_existing_run_numbers,
    _load_existing_step_timings,
    _resolve_resume_start_iteration,
    _sync_run_project_step_config,
)


def _valid_production_project_text(
    tmp_path: Path, healthy_csv: Path, disease_csv: Path, out_dir: Path
) -> str:
    """Minimal project.json that passes load_project and infer_monte_carlo_layout (2 flat groups)."""
    return json.dumps(
        {
            "project_name": "x",
            "output_base": str(out_dir),
            "samples_base_path": str(tmp_path),
            "groups": [
                {"label": "healthy", "sample_paths": [str(healthy_csv)]},
                {"label": "disease", "sample_paths": [str(disease_csv)]},
            ],
            "step_config": {
                "validation": {
                    "train_fraction": 0.8,
                    "n_iterations": 2,
                    "backend_profiles": {
                        "ecdf": {"enabled": True, "params": {}},
                        "tabular_sklearn": {
                            "enabled": True,
                            "params": {"tabular_methods": [{"method": "random_forest", "params": {}}]},
                        },
                        "generative_hybrid": {"enabled": True, "params": {}},
                    },
                }
            },
        }
    )


def test_resolve_resume_start_iteration_auto_and_explicit():
    assert _resolve_resume_start_iteration(None, n_iterations=10, existing_runs=[]) == 0
    assert _resolve_resume_start_iteration(0, n_iterations=10, existing_runs=[]) == 0
    assert _resolve_resume_start_iteration(0, n_iterations=10, existing_runs=[1, 2, 5]) == 4
    assert _resolve_resume_start_iteration(3, n_iterations=10, existing_runs=[1, 2]) == 2


def test_resolve_resume_start_iteration_validates_bounds():
    with pytest.raises(ValueError, match=">= 1"):
        _resolve_resume_start_iteration(-1, n_iterations=5, existing_runs=[1, 2])
    with pytest.raises(ValueError, match="<= n_iterations"):
        _resolve_resume_start_iteration(6, n_iterations=5, existing_runs=[1, 2])


def test_list_existing_run_numbers_and_load_step_timings(tmp_path: Path):
    root = tmp_path / "mc"
    root.mkdir()
    for run_name in ("run_0001", "run_0002", "run_0004", "notes"):
        (root / run_name).mkdir(exist_ok=True)
    assert _list_existing_run_numbers(root) == [1, 2, 4]

    timings = root / "step_timings.csv"
    timings.write_text(
        "step_name,duration_seconds,return_code,run_id,run_dir,n_train_samples,n_val_samples\n"
        "methyl-centroid,4.2,0,run_0001,/tmp/run_0001,10,4\n"
        "methyl-detector,8.0,0,run_0003,/tmp/run_0003,10,4\n",
        encoding="utf-8",
    )
    kept = _load_existing_step_timings(
        timings,
        keep_until_iteration_exclusive=3,
    )
    assert len(kept) == 1
    assert kept[0]["run_id"] == "run_0001"
    assert isinstance(kept[0]["duration_seconds"], float)
    assert isinstance(kept[0]["return_code"], int)


def test_deep_merge_dicts_prefers_updates_and_preserves_other_keys():
    base = {"detection": {"min_samples_pct": 0.8, "debug": True}, "predictor": {"controls": {"foo": 1}}}
    updates = {"detection": {"min_samples_pct": 0.0, "min_samples_abs": 5}, "predictor": {"model_path": "/tmp/m.pkl"}}
    merged = _deep_merge_dicts(base, updates)
    assert merged["detection"]["min_samples_pct"] == 0.0
    assert merged["detection"]["min_samples_abs"] == 5
    assert merged["detection"]["debug"] is True
    assert merged["predictor"]["controls"] == {"foo": 1}
    assert merged["predictor"]["model_path"] == "/tmp/m.pkl"


def test_sync_run_project_step_config_merges_base_into_existing_run_project(tmp_path: Path):
    run_project = tmp_path / "project.json"
    run_project.write_text(
        json.dumps(
            {
                "project_name": "run_0001",
                "step_config": {
                    "detection": {"min_samples_pct": 0.8, "min_samples_abs": 1, "debug": True},
                    "predictor": {"controls": {"groups": []}, "diseases": {"groups": []}},
                },
            }
        ),
        encoding="utf-8",
    )
    base_step_config = {
        "detection": {"min_samples_pct": 0.0, "min_samples_abs": 5},
        "predictor": {"model_path": "/work/model.pkl"},
    }
    changed = _sync_run_project_step_config(run_project, base_step_config)
    assert changed is True
    payload = json.loads(run_project.read_text(encoding="utf-8"))
    assert payload["step_config"]["detection"]["min_samples_pct"] == 0.0
    assert payload["step_config"]["detection"]["min_samples_abs"] == 5
    assert payload["step_config"]["detection"]["debug"] is True
    assert "controls" in payload["step_config"]["predictor"]
    assert payload["step_config"]["predictor"]["model_path"] == "/work/model.pkl"


def test_post_model_validation_requires_production_project(tmp_path: Path, monkeypatch, capsys):
    project = tmp_path / "project.json"
    project.write_text(
        """
{
  "project_name": "x",
  "output_base": "/tmp/out",
  "samples_base_path": "/tmp/samples",
  "groups": [
    {"label": "healthy", "sample_paths": ["healthy.csv"]},
    {"label": "disease", "sample_paths": ["disease.csv"]}
  ],
  "step_config": {
    "validation": {
      "samples_base_path": "/tmp/samples",
      "train_fraction": 0.8,
      "n_iterations": 2
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["methyl-validation", "--project", str(project), "--post-model-validation"],
    )
    with pytest.raises(SystemExit) as ex:
        cli.main()
    assert ex.value.code == 1
    err = capsys.readouterr().err
    assert "requires production project" in err


def test_model_mc_all_requires_model_mc(tmp_path: Path, monkeypatch, capsys):
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\n", encoding="utf-8")
    d.write_text("sample\nD1\n", encoding="utf-8")
    project = tmp_path / "project.json"
    project.write_text(
        f"""
{{
  "project_name": "x",
  "output_base": "{tmp_path.as_posix()}",
  "samples_base_path": "{tmp_path.as_posix()}",
  "groups": [
    {{"label": "healthy", "sample_paths": ["{h.as_posix()}"]}},
    {{"label": "disease", "sample_paths": ["{d.as_posix()}"]}}
  ],
  "step_config": {{
    "validation": {{
      "train_fraction": 0.8,
      "n_iterations": 2,
      "backend_profiles": {{
        "ecdf": {{"enabled": true, "params": {{}}}},
        "tabular_sklearn": {{"enabled": true, "params": {{"tabular_methods": [{{"method": "random_forest", "params": {{}}}}]}}}},
        "generative_hybrid": {{"enabled": true, "params": {{}}}}
      }}
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["methyl-validation", "--project", str(project), "--model-mc-all"],
    )
    with pytest.raises(SystemExit) as ex:
        cli.main()
    assert ex.value.code == 1
    err = capsys.readouterr().err
    assert "--model-mc-all requires --model-mc" in err


def test_skip_detection_runs_stability_only(tmp_path: Path, monkeypatch):
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\n", encoding="utf-8")
    d.write_text("sample\nD1\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    project = tmp_path / "project.json"
    project.write_text(
        f"""
{{
  "project_name": "x",
  "output_base": "{out_dir.as_posix()}",
  "samples_base_path": "{tmp_path.as_posix()}",
  "groups": [
    {{"label": "healthy", "sample_paths": ["{h.as_posix()}"]}},
    {{"label": "disease", "sample_paths": ["{d.as_posix()}"]}}
  ],
  "step_config": {{
    "validation": {{
      "train_fraction": 0.8,
      "n_iterations": 2,
      "backend_profiles": {{
        "ecdf": {{"enabled": true, "params": {{}}}},
        "generative_hybrid": {{"enabled": true, "params": {{}}}}
      }}
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )

    calls: dict[str, object] = {}

    def _fake_stability(**kwargs):
        calls["kwargs"] = kwargs
        return {
            "output_dir": str(out_dir / "x" / "monte_carlo_runs" / "stability"),
            "dmp_stability": {"stable_dmps_at_threshold": 1},
            "gene_stability": {"stable_genes_at_threshold": 0},
            "tiered_stability_enabled": False,
        }

    monkeypatch.setattr(cli, "run_stability_analysis", _fake_stability)
    monkeypatch.setattr(
        "sys.argv",
        ["methyl-validation", "--project", str(project), "--stability", "--skip-detection"],
    )
    cli.main()
    assert "kwargs" in calls
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["monte_carlo_runs_root"] == out_dir / "x" / "monte_carlo_runs"


def test_stability_early_stop_breaks_loop_and_writes_diagnostics(tmp_path: Path, monkeypatch):
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\nH2\n", encoding="utf-8")
    d.write_text("sample\nD1\nD2\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    project = tmp_path / "project.json"
    project.write_text(
        f"""
{{
  "project_name": "x",
  "output_base": "{out_dir.as_posix()}",
  "samples_base_path": "{tmp_path.as_posix()}",
  "groups": [
    {{"label": "healthy", "sample_paths": ["{h.as_posix()}"]}},
    {{"label": "disease", "sample_paths": ["{d.as_posix()}"]}}
  ],
  "step_config": {{
    "validation": {{
      "train_fraction": 0.8,
      "n_iterations": 6,
      "run_stability": true,
      "stability_early_stop_enabled": true,
      "stability_min_iterations": 2,
      "stability_convergence_window": 1,
      "stability_convergence_jaccard": 0.95,
      "stability_convergence_max_size_delta": 0.2,
      "stability_convergence_patience": 2,
      "backend_profiles": {{
        "ecdf": {{"enabled": true, "params": {{}}}},
        "tabular_sklearn": {{"enabled": true, "params": {{"tabular_methods": [{{"method": "random_forest", "params": {{}}}}]}}}},
        "generative_hybrid": {{"enabled": true, "params": {{}}}}
      }}
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )

    state = {"iterations_run": 0, "checkpoints": 0, "stability_kwargs": None}

    monkeypatch.setattr(cli, "infer_monte_carlo_layout", lambda *_args, **_kwargs: "binary")
    monkeypatch.setattr(cli, "load_and_resolve_sample_paths", lambda *_args, **_kwargs: (["H1", "H2"], ["D1", "D2"]))
    monkeypatch.setattr(cli, "stratified_split", lambda *_args, **_kwargs: (["H1"], ["D1"], ["H2"], ["D2"]))
    monkeypatch.setattr(cli, "write_detector_featurecuts_override", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "load_project",
        lambda _path: SimpleNamespace(
            get_comparisons=lambda: [SimpleNamespace(control_group="healthy", disease_group="disease")]
        ),
    )

    def _fake_generate_run_project(*args, **kwargs):
        run_dir = Path(args[1])
        run_dir.mkdir(parents=True, exist_ok=True)
        project_path = run_dir / "project.json"
        project_path.write_text("{}", encoding="utf-8")
        val_control_csv = run_dir / "val_control.csv"
        val_disease_csv = run_dir / "val_disease.csv"
        val_control_csv.write_text("sample\nH2\n", encoding="utf-8")
        val_disease_csv.write_text("sample\nD2\n", encoding="utf-8")
        return project_path, None, None, val_control_csv, val_disease_csv, None, None

    def _fake_run_pipeline_for_iteration(*_args, **kwargs):
        state["iterations_run"] += 1
        logs_dir = Path(kwargs["logs_dir"])
        logs_dir.mkdir(parents=True, exist_ok=True)
        return True, [], []

    def _fake_evaluate_dmp_stability_convergence(*_args, **_kwargs):
        state["checkpoints"] += 1
        return {
            "eligible_for_check": True,
            "converged_checkpoint": True,
            "jaccard": 1.0,
            "relative_size_delta": 0.0,
            "n_runs_analyzed": state["checkpoints"],
        }

    def _fake_stability(**kwargs):
        state["stability_kwargs"] = kwargs
        return {
            "output_dir": str(out_dir / "x" / "monte_carlo_runs" / "stability"),
            "dmp_stability": {"stable_dmps_at_threshold": 1},
            "gene_stability": {"stable_genes_at_threshold": 0},
            "tiered_stability_enabled": False,
        }

    monkeypatch.setattr(cli, "generate_run_project", _fake_generate_run_project)
    monkeypatch.setattr(cli, "run_pipeline_for_iteration", _fake_run_pipeline_for_iteration)
    monkeypatch.setattr(cli, "run_stability_analysis", _fake_stability)
    monkeypatch.setattr(cli, "iteration_scalar_metrics_from_run_dir", lambda _run_dir: {"balanced_accuracy": 0.91})
    monkeypatch.setattr(cli, "evaluate_dmp_stability_convergence", _fake_evaluate_dmp_stability_convergence)
    monkeypatch.setattr(
        "sys.argv",
        ["methyl-validation", "--project", str(project), "--stability"],
    )

    cli.main()
    assert state["iterations_run"] == 2
    assert state["checkpoints"] == 2
    stability_kwargs = state["stability_kwargs"]
    assert isinstance(stability_kwargs, dict)
    early = stability_kwargs["convergence_diagnostics"]
    assert early["enabled"] is True
    assert early["triggered"] is True
    assert early["stopped_after_iteration"] == 2
    assert len(early["checkpoint_history"]) == 2


def test_stability_early_stop_disabled_keeps_full_iteration_budget(tmp_path: Path, monkeypatch):
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\nH2\n", encoding="utf-8")
    d.write_text("sample\nD1\nD2\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    project = tmp_path / "project.json"
    project.write_text(
        f"""
{{
  "project_name": "x",
  "output_base": "{out_dir.as_posix()}",
  "samples_base_path": "{tmp_path.as_posix()}",
  "groups": [
    {{"label": "healthy", "sample_paths": ["{h.as_posix()}"]}},
    {{"label": "disease", "sample_paths": ["{d.as_posix()}"]}}
  ],
  "step_config": {{
    "validation": {{
      "train_fraction": 0.8,
      "n_iterations": 3,
      "run_stability": true,
      "stability_early_stop_enabled": false,
      "backend_profiles": {{
        "ecdf": {{"enabled": true, "params": {{}}}},
        "tabular_sklearn": {{"enabled": true, "params": {{"tabular_methods": [{{"method": "random_forest", "params": {{}}}}]}}}},
        "generative_hybrid": {{"enabled": true, "params": {{}}}}
      }}
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )

    state = {"iterations_run": 0}
    monkeypatch.setattr(cli, "infer_monte_carlo_layout", lambda *_args, **_kwargs: "binary")
    monkeypatch.setattr(cli, "load_and_resolve_sample_paths", lambda *_args, **_kwargs: (["H1", "H2"], ["D1", "D2"]))
    monkeypatch.setattr(cli, "stratified_split", lambda *_args, **_kwargs: (["H1"], ["D1"], ["H2"], ["D2"]))
    monkeypatch.setattr(cli, "write_detector_featurecuts_override", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "load_project",
        lambda _path: SimpleNamespace(
            get_comparisons=lambda: [SimpleNamespace(control_group="healthy", disease_group="disease")]
        ),
    )

    def _fake_generate_run_project(*args, **kwargs):
        run_dir = Path(args[1])
        run_dir.mkdir(parents=True, exist_ok=True)
        project_path = run_dir / "project.json"
        project_path.write_text("{}", encoding="utf-8")
        val_control_csv = run_dir / "val_control.csv"
        val_disease_csv = run_dir / "val_disease.csv"
        val_control_csv.write_text("sample\nH2\n", encoding="utf-8")
        val_disease_csv.write_text("sample\nD2\n", encoding="utf-8")
        return project_path, None, None, val_control_csv, val_disease_csv, None, None

    def _fake_run_pipeline_for_iteration(*_args, **kwargs):
        state["iterations_run"] += 1
        logs_dir = Path(kwargs["logs_dir"])
        logs_dir.mkdir(parents=True, exist_ok=True)
        return True, [], []

    monkeypatch.setattr(cli, "generate_run_project", _fake_generate_run_project)
    monkeypatch.setattr(cli, "run_pipeline_for_iteration", _fake_run_pipeline_for_iteration)
    monkeypatch.setattr(cli, "iteration_scalar_metrics_from_run_dir", lambda _run_dir: {"balanced_accuracy": 0.91})
    monkeypatch.setattr(
        cli,
        "evaluate_dmp_stability_convergence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("early-stop evaluator should not be called")),
    )
    monkeypatch.setattr(
        cli,
        "run_stability_analysis",
        lambda **_kwargs: {
            "output_dir": str(out_dir / "x" / "monte_carlo_runs" / "stability"),
            "dmp_stability": {"stable_dmps_at_threshold": 1},
            "gene_stability": {"stable_genes_at_threshold": 0},
            "tiered_stability_enabled": False,
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        ["methyl-validation", "--project", str(project), "--stability"],
    )

    cli.main()
    assert state["iterations_run"] == 3


def test_model_mc_all_uses_shared_stage(tmp_path: Path, monkeypatch):
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\nH2\n", encoding="utf-8")
    d.write_text("sample\nD1\nD2\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    production_dir = out_dir / "x" / "monte_carlo_runs" / "production"
    production_dir.mkdir(parents=True, exist_ok=True)
    (production_dir / "project.json").write_text(
        _valid_production_project_text(tmp_path, h, d, out_dir), encoding="utf-8"
    )
    project = tmp_path / "project.json"
    project.write_text(
        f"""
{{
  "project_name": "x",
  "output_base": "{out_dir.as_posix()}",
  "samples_base_path": "{tmp_path.as_posix()}",
  "groups": [
    {{"label": "healthy", "sample_paths": ["{h.as_posix()}"]}},
    {{"label": "disease", "sample_paths": ["{d.as_posix()}"]}}
  ],
  "step_config": {{
    "validation": {{
      "train_fraction": 0.8,
      "n_iterations": 2,
      "backend_profiles": {{
        "ecdf": {{"enabled": true, "params": {{}}}},
        "tabular_sklearn": {{"enabled": true, "params": {{"tabular_methods": [{{"method": "random_forest", "params": {{}}}}]}}}},
        "generative_hybrid": {{"enabled": true, "params": {{}}}}
      }}
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )

    calls = {"shared": 0, "backends": []}

    def _fake_shared(**kwargs):
        calls["shared"] += 1
        return [
            {
                "iteration": 1,
                "run_id": "run_0001",
                "run_dir": str(tmp_path / "shared" / "run_0001"),
                "project_json": str(tmp_path / "shared" / "run_0001" / "project.json"),
                "n_train_samples": 2,
                "n_val_samples": 2,
            }
        ]

    def _fake_backend(**kwargs):
        calls["backends"].append(kwargs["backend"])

    monkeypatch.setattr(cli, "_build_model_mc_shared_runs", _fake_shared)
    monkeypatch.setattr(cli, "_run_model_mc_backend_from_shared_runs", _fake_backend)
    monkeypatch.setattr(
        "sys.argv",
        ["methyl-validation", "--project", str(project), "--model-mc", "--model-mc-all"],
    )
    cli.main()
    assert calls["shared"] == 1
    assert calls["backends"] == ["ecdf", "tabular_sklearn", "generative_hybrid"]


def test_select_best_model_ignores_shared_directory(tmp_path: Path, monkeypatch):
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\nH2\n", encoding="utf-8")
    d.write_text("sample\nD1\nD2\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    model_mc_root = out_dir / "x" / "monte_carlo_runs" / "model_mc"
    production_dir = out_dir / "x" / "monte_carlo_runs" / "production"
    production_dir.mkdir(parents=True, exist_ok=True)
    (production_dir / "project.json").write_text(
        _valid_production_project_text(tmp_path, h, d, out_dir), encoding="utf-8"
    )
    (model_mc_root / "shared").mkdir(parents=True, exist_ok=True)
    for backend in ("ecdf", "tabular_sklearn", "generative_hybrid"):
        root = model_mc_root / backend
        root.mkdir(parents=True, exist_ok=True)
        (root / "metrics_summary.json").write_text(
            '{"balanced_accuracy": {"mean": 0.7, "percentiles": {"p50": 0.7}}}',
            encoding="utf-8",
        )
    project = tmp_path / "project.json"
    project.write_text(
        f"""
{{
  "project_name": "x",
  "output_base": "{out_dir.as_posix()}",
  "samples_base_path": "{tmp_path.as_posix()}",
  "groups": [
    {{"label": "healthy", "sample_paths": ["{h.as_posix()}"]}},
    {{"label": "disease", "sample_paths": ["{d.as_posix()}"]}}
  ],
  "step_config": {{
    "validation": {{
      "train_fraction": 0.8,
      "n_iterations": 2,
      "backend_profiles": {{
        "ecdf": {{"enabled": true, "params": {{}}}},
        "generative_hybrid": {{"enabled": true, "params": {{}}}}
      }}
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )

    captured: dict[str, list[str]] = {}

    def _fake_rank(**kwargs):
        captured["backends"] = list(kwargs["backends"])
        return [
            {"backend": "ecdf", "metric": "balanced_accuracy", "stat": "median", "score": 0.8, "rank": 1}
        ]

    monkeypatch.setattr(cli, "_write_backend_ranking", _fake_rank)
    monkeypatch.setattr(
        cli,
        "build_production_model",
        lambda **kwargs: {"success": True, "output_dir": str(production_dir)},
    )
    monkeypatch.setattr(
        "sys.argv",
        ["methyl-validation", "--project", str(project), "--select-best-model", "--model-mc-all"],
    )
    cli.main()
    assert set(captured.get("backends", [])) == {"ecdf", "tabular_sklearn", "generative_hybrid"}


def test_model_mc_single_backend_reuses_existing_shared_runs(tmp_path: Path, monkeypatch):
    h = tmp_path / "healthy.csv"
    d = tmp_path / "disease.csv"
    h.write_text("sample\nH1\nH2\n", encoding="utf-8")
    d.write_text("sample\nD1\nD2\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    production_dir = out_dir / "x" / "monte_carlo_runs" / "production"
    production_dir.mkdir(parents=True, exist_ok=True)
    (production_dir / "project.json").write_text(
        _valid_production_project_text(tmp_path, h, d, out_dir), encoding="utf-8"
    )
    shared_run_dir = out_dir / "x" / "monte_carlo_runs" / "model_mc" / "shared" / "run_0001"
    shared_run_dir.mkdir(parents=True, exist_ok=True)
    (shared_run_dir / "project.json").write_text("{}", encoding="utf-8")
    project = tmp_path / "project.json"
    project.write_text(
        f"""
{{
  "project_name": "x",
  "output_base": "{out_dir.as_posix()}",
  "samples_base_path": "{tmp_path.as_posix()}",
  "groups": [
    {{"label": "healthy", "sample_paths": ["{h.as_posix()}"]}},
    {{"label": "disease", "sample_paths": ["{d.as_posix()}"]}}
  ],
  "step_config": {{
    "validation": {{
      "train_fraction": 0.8,
      "n_iterations": 2,
      "backend_profiles": {{
        "ecdf": {{"enabled": true, "params": {{}}}},
        "generative_hybrid": {{"enabled": true, "params": {{}}}}
      }}
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )

    calls = {"shared_runner": 0, "legacy_runner": 0}

    def _fake_shared_runner(**kwargs):
        calls["shared_runner"] += 1

    def _fake_legacy_runner(**kwargs):
        calls["legacy_runner"] += 1

    monkeypatch.setattr(cli, "_run_model_mc_backend_from_shared_runs", _fake_shared_runner)
    monkeypatch.setattr(cli, "_run_model_mc_backend", _fake_legacy_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "methyl-validation",
            "--project",
            str(project),
            "--model-mc",
            "--model-backend",
            "generative_hybrid",
        ],
    )
    cli.main()
    assert calls["shared_runner"] == 1
    assert calls["legacy_runner"] == 0


def test_build_model_mc_shared_runs_symlinks_reusable_primary_runs(tmp_path: Path, monkeypatch):
    primary_root = tmp_path / "primary_mc"
    run1 = primary_root / "run_0001"
    (run1 / "detections" / "all" / "pca_pca1").mkdir(parents=True, exist_ok=True)
    (run1 / "centroids").mkdir(parents=True, exist_ok=True)
    (run1 / "project.json").write_text("{}", encoding="utf-8")
    (primary_root / "step_timings.csv").write_text(
        "step_name,duration_seconds,return_code,run_id,run_dir,n_train_samples,n_val_samples\n"
        "methyl-detector,12.0,0,run_0001,/tmp/run_0001,8,2\n",
        encoding="utf-8",
    )

    calls = {"generated_project": 0, "ran_pipeline": 0}

    def _fake_resolve_iteration_split(**kwargs):
        return (["h1", "h2"], ["d1", "d2"], ["h3"], ["d3"]), "reused"

    def _fake_generate_run_project(
        base_project_path,
        run_dir,
        run_id,
        output_base,
        train_control,
        train_disease,
        val_control,
        val_disease,
        samples_base_path,
    ):
        calls["generated_project"] += 1
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        project_path = run_dir / "project.json"
        project_path.write_text("{}", encoding="utf-8")
        return (
            project_path,
            run_dir / "training_control.csv",
            run_dir / "training_disease.csv",
            run_dir / "testing_control.csv",
            run_dir / "testing_disease.csv",
            None,
            None,
        )

    def _forbidden_run_pipeline(*args, **kwargs):
        calls["ran_pipeline"] += 1
        raise AssertionError("run_pipeline_for_iteration should not be called when reusable run exists")

    monkeypatch.setattr(cli, "resolve_iteration_split", _fake_resolve_iteration_split)
    monkeypatch.setattr(cli, "generate_run_project", _fake_generate_run_project)
    monkeypatch.setattr(cli, "run_pipeline_for_iteration", _forbidden_run_pipeline)

    config = SimpleNamespace(
        n_iterations=1,
        train_fraction=0.8,
        seed=42,
        samples_base_path=str(tmp_path),
        abort_on_step_failure=True,
    )
    shared_root = tmp_path / "model_mc" / "shared"
    rows = cli._build_model_mc_shared_runs(
        base_project_for_runs=tmp_path / "production_project.json",
        config=config,
        layout="binary",
        cohort_paths_list=[("healthy", ["h1", "h2", "h3"]), ("disease", ["d1", "d2", "d3"])],
        cohort_labels=["healthy", "disease"],
        control_paths=["h1", "h2", "h3"],
        disease_paths=["d1", "d2", "d3"],
        shared_root=shared_root,
        resume_arg=None,
        per_cancer_group=False,
        primary_monte_carlo_runs_root=primary_root,
    )

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run_0001"
    linked_run = shared_root / "run_0001"
    assert linked_run.is_dir()
    assert not linked_run.is_symlink()
    assert (linked_run / "project.json").is_file()
    assert (linked_run / "centroids").is_symlink()
    assert (linked_run / "detections").is_symlink()
    assert (linked_run / "centroids").resolve() == (run1 / "centroids").resolve()
    assert (linked_run / "detections").resolve() == (run1 / "detections").resolve()
    assert calls["generated_project"] == 1
    assert calls["ran_pipeline"] == 0


def test_run_model_mc_backend_reuses_primary_centroid_detector_artifacts(tmp_path: Path, monkeypatch):
    primary_root = tmp_path / "primary_mc"
    run1 = primary_root / "run_0001"
    (run1 / "detections" / "all" / "pca_pca1").mkdir(parents=True, exist_ok=True)
    (run1 / "centroids").mkdir(parents=True, exist_ok=True)
    (run1 / "project.json").write_text("{}", encoding="utf-8")
    (primary_root / "step_timings.csv").write_text(
        "step_name,duration_seconds,return_code,run_id,run_dir,n_train_samples,n_val_samples\n"
        "methyl-detector,9.0,0,run_0001,/tmp/run_0001,8,2\n",
        encoding="utf-8",
    )

    calls = {"generated_project": 0, "ran_detector_stage": 0, "ran_model_stage": 0}

    def _fake_resolve_iteration_split(**kwargs):
        return (["h1", "h2"], ["d1", "d2"], ["h3"], ["d3"]), "reused"

    def _fake_generate_run_project(
        base_project_path,
        run_dir,
        run_id,
        output_base,
        train_control,
        train_disease,
        val_control,
        val_disease,
        samples_base_path,
    ):
        calls["generated_project"] += 1
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        project_path = run_dir / "project.json"
        project_path.write_text("{}", encoding="utf-8")
        return (
            project_path,
            run_dir / "training_control.csv",
            run_dir / "training_disease.csv",
            run_dir / "testing_control.csv",
            run_dir / "testing_disease.csv",
            None,
            None,
        )

    def _forbidden_run_pipeline(*args, **kwargs):
        calls["ran_detector_stage"] += 1
        raise AssertionError("run_pipeline_for_iteration should not be called when reusable run exists")

    def _fake_run_pipeline_for_model(**kwargs):
        calls["ran_model_stage"] += 1
        pred_dir = Path(kwargs["predictor_output_dir"])
        pred_dir.mkdir(parents=True, exist_ok=True)
        (pred_dir / "validation_metrics.json").write_text(
            json.dumps({"balanced_accuracy": 0.9}),
            encoding="utf-8",
        )
        return True, [], []

    class _Cfg(SimpleNamespace):
        def with_backend_selection(self, _backend):
            return self

    monkeypatch.setattr(cli, "resolve_iteration_split", _fake_resolve_iteration_split)
    monkeypatch.setattr(cli, "generate_run_project", _fake_generate_run_project)
    monkeypatch.setattr(cli, "run_pipeline_for_iteration", _forbidden_run_pipeline)
    monkeypatch.setattr(cli, "run_pipeline_for_model", _fake_run_pipeline_for_model)
    monkeypatch.setattr(cli, "_write_model_mc_outputs", lambda **kwargs: None)
    monkeypatch.setattr(cli, "iteration_scalar_metrics_from_run_dir", lambda _run_dir: {"balanced_accuracy": 0.9})
    monkeypatch.setattr(
        cli,
        "load_project",
        lambda _path: SimpleNamespace(
            get_comparisons=lambda: [
                SimpleNamespace(control_group="healthy", disease_group="disease")
            ]
        ),
    )

    config = _Cfg(
        n_iterations=1,
        train_fraction=0.8,
        seed=42,
        samples_base_path=str(tmp_path),
        abort_on_step_failure=True,
    )
    backend_root = tmp_path / "model_mc" / "ecdf"
    cli._run_model_mc_backend(
        backend="ecdf",
        base_project_for_runs=tmp_path / "production_project.json",
        config=config,
        layout="binary",
        cohort_paths_list=[("healthy", ["h1", "h2", "h3"]), ("disease", ["d1", "d2", "d3"])],
        cohort_labels=["healthy", "disease"],
        control_paths=["h1", "h2", "h3"],
        disease_paths=["d1", "d2", "d3"],
        backend_root=backend_root,
        resume_arg=None,
        per_cancer_group=False,
        primary_monte_carlo_runs_root=primary_root,
    )

    linked_run = backend_root / "run_0001"
    assert linked_run.is_dir()
    assert (linked_run / "centroids").is_symlink()
    assert (linked_run / "detections").is_symlink()
    assert (linked_run / "centroids").resolve() == (run1 / "centroids").resolve()
    assert (linked_run / "detections").resolve() == (run1 / "detections").resolve()
    assert calls["generated_project"] == 1
    assert calls["ran_detector_stage"] == 0
    assert calls["ran_model_stage"] == 1
