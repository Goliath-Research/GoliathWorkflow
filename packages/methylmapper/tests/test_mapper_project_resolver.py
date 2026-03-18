"""Regression tests for comparison-aware mapper path resolution."""

import json
from pathlib import Path

from methyl_mapper.project_resolver import (
    DMP_CSV_PATTERN_BIOLOGICAL,
    resolve_mapper_paths,
    resolve_mapper_paths_per_cancer_group,
)


def _write_project(tmp_path: Path) -> Path:
    project_path = tmp_path / "project.json"
    project_path.write_text(
        json.dumps(
            {
                "project_name": "MapperProject",
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
                "step_config": {"mapper": {"csv_pattern": "dmps-*.csv"}},
            }
        ),
        encoding="utf-8",
    )
    return project_path


def test_resolve_mapper_paths_uses_comparison_wildcards(tmp_path):
    project_path = _write_project(tmp_path)

    paths = resolve_mapper_paths(project_path)

    assert paths.csv_pattern == "/work/output/MapperProject/detections/*/*/dmps-*.csv"
    assert paths.output_dir == "/work/output/MapperProject/mapper"


def test_resolve_mapper_paths_per_comparison_uses_canonical_layout(tmp_path):
    project_path = _write_project(tmp_path)

    resolved = resolve_mapper_paths_per_cancer_group(
        project_path,
        csv_filename_pattern=DMP_CSV_PATTERN_BIOLOGICAL,
    )

    assert len(resolved) == 1
    paths, label = resolved[0]
    assert label == "pca"
    assert (
        paths.csv_pattern
        == "/work/output/MapperProject/detections/healthy/pca/dmps-*.csv"
    )
    assert paths.output_dir == "/work/output/MapperProject/mapper/healthy/pca"
