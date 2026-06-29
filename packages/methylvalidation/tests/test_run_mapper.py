from __future__ import annotations

from pathlib import Path

from methyl_validation import pipeline_runner


def test_run_mapper_does_not_pass_per_cancer_group(monkeypatch, tmp_path: Path):
    captured: dict[str, list[str]] = {}

    def _fake_run_cmd(cmd):
        captured["cmd"] = list(cmd)
        return 0, "ok", ""

    monkeypatch.setattr(pipeline_runner, "run_cmd", _fake_run_cmd)
    monkeypatch.setattr(pipeline_runner, "_mapper_override_dict", lambda _p: {})

    project_json = tmp_path / "run_0001" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text("{}", encoding="utf-8")

    rc, out, err = pipeline_runner.run_mapper(project_json, per_cancer_group=True)
    assert rc == 0
    assert captured["cmd"] == ["methyl-mapper", "--project", str(project_json)]
    assert "--per-cancer-group" not in captured["cmd"]


def test_run_mapper_passes_mapper_step_override_from_resolved_config(monkeypatch, tmp_path: Path):
    captured: dict[str, list[str]] = {}

    def _fake_run_cmd(cmd):
        captured["cmd"] = list(cmd)
        return 0, "ok", ""

    monkeypatch.setattr(pipeline_runner, "run_cmd", _fake_run_cmd)

    run_dir = tmp_path / "run_0001"
    run_dir.mkdir(parents=True)
    project_json = run_dir / "project.json"
    project_json.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        pipeline_runner,
        "_mapper_override_dict",
        lambda _p: {"csv_filename_pattern": "dmps-*-classifier-extended.csv"},
    )

    pipeline_runner.run_mapper(project_json)
    assert captured["cmd"][0:3] == ["methyl-mapper", "--project", str(project_json)]
    assert "--step-override" in captured["cmd"]
