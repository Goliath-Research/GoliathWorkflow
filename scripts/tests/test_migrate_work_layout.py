"""Tests for scripts/migrate_work_layout.py (tmpdir only; does not touch /work)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from migrate_work_layout import (  # noqa: E402
    MigrationConfig,
    remap_artifacts,
    remap_study_manifests,
    run_preflight,
    run_verify,
)


@pytest.fixture
def layout(tmp_path: Path) -> MigrationConfig:
    work = tmp_path / "work"
    old = work / "prostate-cancer"
    new = work / "projects" / "prostate-cancer"
    old.mkdir(parents=True)
    (work / "epimethyl").mkdir()
    (work / "samples").mkdir()
    (work / "genomes").mkdir()
    (work / "cache").mkdir()
    (work / "site").mkdir()
    (old / "configs").mkdir(parents=True)
    (old / "data").mkdir()
    proj = old / "configs" / "project_Test.json"
    proj.write_text(
        json.dumps(
            {
                "project_name": "Test",
                "output_base": str(old),
                "samples_base_path": str(work / "samples"),
                "path_remap": {"/lambda/nfs/Work/prostate-cancer": str(old)},
                "controls": {"label": "healthy", "groups": []},
                "diseases": {"label": "cancer", "groups": []},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    run_dir = old / "Test" / "monte_carlo_runs" / "run_0001"
    run_dir.mkdir(parents=True)
    (run_dir / "project.json").write_text(
        json.dumps({"output_base": str(old), "project_name": "Test"}) + "\n",
        encoding="utf-8",
    )
    return MigrationConfig(
        work_root=work,
        old_disease_root=old,
        new_disease_root=new,
        site_manifest=work / "site" / "methyl_site.json",
        path_remap_old=str(old),
        path_remap_new=str(new),
    )


def test_preflight_lists_source(layout: MigrationConfig) -> None:
    report = run_preflight(layout)
    assert report.source_exists
    assert report.platform_dirs["epimethyl"]
    assert "configs" in report.source_children


def test_remap_study_manifest_and_artifacts(layout: MigrationConfig) -> None:
    import shutil

    shutil.copytree(layout.old_disease_root, layout.new_disease_root)
    layout.site_manifest.write_text('{"actionConfig":{}}\n', encoding="utf-8")
    remap_study_manifests(layout, dry_run=False)
    proj = layout.new_disease_root / "configs" / "project_Test.json"
    data = json.loads(proj.read_text(encoding="utf-8"))
    assert data["output_base"] == str(layout.new_disease_root)
    assert data["path_remap"][str(layout.old_disease_root)] == str(layout.new_disease_root)

    remap_artifacts(layout, dry_run=False)
    nested = layout.new_disease_root / "Test" / "monte_carlo_runs" / "run_0001" / "project.json"
    nested_data = json.loads(nested.read_text(encoding="utf-8"))
    assert nested_data["output_base"] == str(layout.new_disease_root)

    assert run_verify(layout) == 0
