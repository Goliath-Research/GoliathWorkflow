from __future__ import annotations

from pathlib import Path

import pytest

from methyl_validation import cli
from methyl_validation.cli import (
    _list_existing_run_numbers,
    _load_existing_step_timings,
    _resolve_resume_start_iteration,
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
