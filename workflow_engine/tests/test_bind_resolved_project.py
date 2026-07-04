"""Tests for ResolvedProject path binding in materialize_action_input."""

from __future__ import annotations

import sys
from pathlib import Path

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))

from workflow_context import bind_resolved_project_paths, materialize_action_input


def test_bind_resolved_project_paths_sets_detector_output_dir() -> None:
    bound = bind_resolved_project_paths(
        {"tool": "MethylDetector", "comparison": "PCa"},
        {
            "resolvedProject": {
                "comparisons": [
                    {
                        "label": "PCa",
                        "comparisonLabel": "PCa",
                        "diseaseGroup": "PCa",
                        "centroid1Dir": "/work/c1",
                        "centroid2Dir": "/work/c2",
                        "detectOutDir": "/work/detect/PCa",
                        "mapperOutDir": "/work/mapper/PCa",
                        "enricherOutDir": "/work/enricher/PCa",
                    }
                ]
            }
        },
    )
    assert bound["outputDir"] == "/work/detect/PCa"
    assert bound["centroid1Dir"] == "/work/c1"
    assert bound["centroid2Dir"] == "/work/c2"


def test_materialize_action_input_preserves_existing_output_dir() -> None:
    out = materialize_action_input(
        {
            "tool": "MethylEnricher",
            "projectPath": "/work/p.json",
            "outputDir": "/explicit/out",
            "comparison": "PCa",
        },
        "pipeline.enricher",
        {
            "resolvedProject": {
                "comparisons": [
                    {
                        "label": "PCa",
                        "diseaseGroup": "PCa",
                        "enricherOutDir": "/work/enricher/PCa",
                    }
                ]
            },
            "actionConfig": {"enricher": {"ppi_only": True}},
        },
    )
    assert out["outputDir"] == "/explicit/out"
    assert out["resolvedConfig"]["ppi_only"] is True
