from __future__ import annotations

from pathlib import Path

from methyl_validation import pipeline_runner


def test_run_mapper_does_not_pass_per_cancer_group(monkeypatch):
    captured: dict[str, list[str]] = {}

    def _fake_run_cmd(cmd):
        captured["cmd"] = list(cmd)
        return 0, "ok", ""

    monkeypatch.setattr(pipeline_runner, "run_cmd", _fake_run_cmd)

    rc, out, err = pipeline_runner.run_mapper(Path("/tmp/run_0001/project.json"), per_cancer_group=True)
    assert rc == 0
    assert captured["cmd"] == ["methyl-mapper", "--project", "/tmp/run_0001/project.json"]
    assert "--per-cancer-group" not in captured["cmd"]
