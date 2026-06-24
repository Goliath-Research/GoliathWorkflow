"""Manifest-first collector behavior for pipeline CLI actions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_domain.action_result import atomic_write_json, manifest_path_for
from methyl_worker.collectors import (
    CentroidLegacyCollector,
    DetectorLegacyCollector,
    EnricherLegacyCollector,
    ManifestFirstCollector,
)
from methyl_worker.task_models.pipeline_models import (
    CentroidTaskOutput,
    DetectorTaskOutput,
    EnricherTaskOutput,
)


def test_manifest_first_collector_reads_detector_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "detections"
    out_dir.mkdir()
    input_json = {"chromosome": "21", "context": "CG", "group": "pca1", "outputDir": str(out_dir)}
    manifest = manifest_path_for(out_dir, "pipeline.detector", "21_CG_pca1")
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "status": "ok",
            "action_name": "pipeline.detector",
            "chromosome": "21",
            "context": "CG",
            "group": "pca1",
            "output_dir": str(out_dir),
            "n_statistical_dmps": 100,
            "n_biological_dmps": 42,
            "result_code": 0,
        },
    )
    collector = ManifestFirstCollector(
        output_model=DetectorTaskOutput,
        resolve_output_dir=lambda inp: inp.get("outputDir"),
        legacy_collect=DetectorLegacyCollector(),
    )
    payload = collector.collect(input_json, action_name="pipeline.detector")
    assert payload["n_statistical_dmps"] == 100
    assert payload["manifest_path"] == str(manifest)


def test_manifest_first_collector_falls_back_to_centroid_legacy(tmp_path: Path) -> None:
    out_dir = tmp_path / "centroids"
    out_dir.mkdir()
    h5 = out_dir / "21-CG.h5"
    h5.write_bytes(b"stub")
    input_json = {
        "chromosome": "21",
        "context": "CG",
        "group": "healthy",
        "outputDir": str(out_dir),
    }
    collector = ManifestFirstCollector(
        output_model=CentroidTaskOutput,
        resolve_output_dir=lambda inp: inp.get("outputDir"),
        legacy_collect=CentroidLegacyCollector(),
    )
    payload = collector.collect(input_json, action_name="pipeline.centroid")
    assert payload["centroid_h5_path"] == str(h5)
    assert payload.get("manifest_path") is None


def test_enricher_legacy_collector_reads_completeness_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project.json"
    project.write_text("{}", encoding="utf-8")
    root = tmp_path / "prod" / "enricher"
    root.mkdir(parents=True)
    manifest_path = root / "enricher_completeness.json"
    manifest_path.write_text(
        json.dumps({"all_complete": True, "comparisons": {"healthy_vs_pca1": {"complete": True}}}),
        encoding="utf-8",
    )

    def _fake_root(_project: Path) -> Path:
        return root

    monkeypatch.setattr(
        "methyl_enricher.enricher_completeness.production_enricher_root",
        _fake_root,
    )
    collector = EnricherLegacyCollector()
    payload = collector.collect(
        {"projectPath": str(project), "comparison": "healthy_vs_pca1"},
        action_name="pipeline.enricher",
    )
    assert payload["all_complete"] is True
    assert payload["n_comparisons"] == 1
