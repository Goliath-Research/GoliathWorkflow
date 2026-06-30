"""Subcluster centroid path must honor CLI/worker output_dir and chr/context filters."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from methyl_centroid.project_resolver import _run_cluster_then_centroids_per_cluster


def _write_subcluster_project(path: Path) -> None:
    root = path.parent
    samples = root / "samples"
    samples.mkdir(parents=True)
    sample = samples / "S1"
    sample.mkdir()
    (sample / "1-CG.h5").write_bytes(b"")
    (sample / "2-CG.h5").write_bytes(b"")
    csv_path = root / "cohort.csv"
    csv_path.write_text(f"{sample}\n", encoding="utf-8")
    path.write_text(
        json.dumps(
            {
                "project_name": "subcluster_demo",
                "output_base": str(root),
                "samples_base_path": str(samples),
                "controls": {
                    "label": "healthy",
                    "groups": [
                        {
                            "label": "all",
                            "sample_paths": [str(csv_path)],
                            "subcluster": {
                                "enabled": True,
                                "persist_centroids": True,
                            },
                        }
                    ],
                },
                "diseases": {
                    "label": "cancer",
                    "groups": [{"label": "PCa", "sample_paths": [str(csv_path)]}],
                },
                "comparisons": [{"control_group": "all", "disease_group": "PCa"}],
                "chromosomes": ["1", "2"],
                "contexts": ["CG", "CHG"],
            }
        ),
        encoding="utf-8",
    )


def _write_cluster_manifest(project: Path) -> None:
    from methyl_utils import load_project

    cfg = load_project(project)
    clustering_dir = Path(cfg.get_clustering_output_dir("control", "all"))
    clustering_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "derived_labels": ["cluster_a"],
        "groups": {"cluster_a": [str(project.parent / "samples" / "S1")]},
    }
    (clustering_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_subcluster_centroid_path_honors_chr_context_and_output_dir(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    _write_subcluster_project(project)
    _write_cluster_manifest(project)
    override_out = tmp_path / "custom" / "centroids" / "all"
    captured: list = []

    def _capture_batch(batch):
        captured.append(batch)

    with patch("methyl_centroid.cli.run_batch_processing", side_effect=_capture_batch):
        _run_cluster_then_centroids_per_cluster(
            project,
            "control",
            "all",
            output_dir=override_out,
            chromosome="1",
            context="CG",
        )

    assert len(captured) == 1
    batch = captured[0]
    assert batch.chromosomes == ["1"]
    assert batch.contexts == ["CG"]
    assert batch.base_config.output_dir == str(override_out.resolve())
