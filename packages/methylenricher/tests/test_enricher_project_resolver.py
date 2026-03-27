"""Regression tests for comparison-aware enricher path resolution."""

import json
from pathlib import Path

import pytest

from methyl_enricher.project_resolver import (
    resolve_enricher_paths,
    resolve_enricher_paths_per_cancer_group,
)


def _write_project(tmp_path: Path) -> Path:
    project_path = tmp_path / "project.json"
    project_path.write_text(
        json.dumps(
            {
                "project_name": "EnricherProject",
                "output_base": "/work/output",
                "controls": {
                    "label": "controls",
                    "groups": [{"label": "healthy", "sample_paths": ["c1"]}],
                },
                "diseases": {
                    "label": "diseases",
                    "groups": [{"label": "pca", "sample_paths": ["d1"]}],
                },
                "comparisons": [{"control_group": "healthy", "disease_group": "pca"}],
            }
        ),
        encoding="utf-8",
    )
    return project_path


def test_resolve_enricher_paths_defaults_to_project_roots(tmp_path):
    project_path = _write_project(tmp_path)

    paths = resolve_enricher_paths(project_path)

    assert paths.input_file == "/work/output/EnricherProject/mapper/all-gene_name-combined.csv"
    assert paths.output_dir == "/work/output/EnricherProject/enricher"


def test_resolve_enricher_paths_per_comparison_uses_canonical_layout(tmp_path):
    project_path = _write_project(tmp_path)

    resolved = resolve_enricher_paths_per_cancer_group(project_path)

    assert len(resolved) == 1
    paths, label = resolved[0]
    assert label == "pca"
    assert (
        paths.input_file
        == "/work/output/EnricherProject/mapper/healthy/pca/all-gene_name-combined.csv"
    )
    assert paths.output_dir == "/work/output/EnricherProject/enricher/healthy/pca"


def test_resolve_enricher_paths_warns_on_legacy_alias_keys(tmp_path):
    project_path = _write_project(tmp_path)
    override_path = tmp_path / "override.json"
    override_path.write_text(
        json.dumps({"input": "/tmp/legacy.csv", "outdir": "/tmp/legacy-out"}),
        encoding="utf-8",
    )

    with pytest.warns(DeprecationWarning):
        paths = resolve_enricher_paths(project_path, step_override_path=override_path)

    assert paths.input_file == "/tmp/legacy.csv"
    assert paths.output_dir == "/tmp/legacy-out"
