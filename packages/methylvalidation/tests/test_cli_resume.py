from __future__ import annotations

import json
from pathlib import Path

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
      "n_iterations": 2
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
      "n_iterations": 2
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
      "n_iterations": 2
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
      "n_iterations": 2
    }}
  }}
}}
""".strip(),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

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
    assert set(captured["backends"]) == {"ecdf", "tabular_sklearn", "generative_hybrid"}


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
      "n_iterations": 2
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
