"""Alzheimer cfDNA disease pack: staged manifest resolution + neuro-core preset checks.

The Alzheimer pack is config on the existing methylation control plane (no new actions
or programs), so these tests assert the staged manifest resolves the expected
comparisons/progression and that the committed neuro-core enrichment preset resolves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (
    _REPO / "packages" / "methylutils",
    _REPO / "packages" / "methylenricher",
    _REPO / "workflow_engine",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_CHECK_MANIFEST = (
    _REPO
    / "workflow_engine"
    / "domain"
    / "checks"
    / "alzheimer_cfdna"
    / "configs"
    / "project_Healthy_vs_AD_Stages.json"
)
_EXAMPLE_DIR = _REPO / "docs" / "examples" / "samd" / "alzheimer-cfdna"


def test_staged_manifest_resolves_control_vs_each_stage() -> None:
    from methyl_utils import load_project

    project = load_project(str(_CHECK_MANIFEST))
    assert project.get_primary_modality() == "methylation"
    assert project.get_primary_analyte() == "cfdna"

    comparisons = project.get_comparisons()
    disease_groups = sorted(c.disease_group for c in comparisons)
    assert disease_groups == ["AD_AD", "AD_MCI"]
    assert all(c.control_group == "all" for c in comparisons)
    assert project.progression_labels == ["AD_MCI", "AD_AD"]


def test_neuro_core_preset_resolves_from_registry() -> None:
    from methyl_enricher.preset_registry import load_catalog

    catalog = load_catalog()
    assert "neuro-core" in catalog.presets
    libs = catalog.resolve("neuro-core")
    # Neuro/CNS-specific sets present; oncology-only drug libraries absent.
    assert "Allen_Brain_Atlas_up" in libs
    assert "DSigDB" not in libs
    # Disease priors retained.
    assert "DisGeNET" in libs


def test_disease_overlay_selects_neuro_core_and_alzheimer_term() -> None:
    overlay = json.loads((_EXAMPLE_DIR / "context_alzheimer_cfdna.json").read_text())
    assert overlay["pipelineProcedure"] == "cfdna_wgbs_plasma"
    ac = overlay["actionConfig"]
    assert ac["mapper"]["disease_term"] == "Alzheimer's disease"
    assert ac["mapper"]["enrich_disease"] is True
    assert ac["enricher"]["library_preset"] == "neuro-core"
    assert overlay["runProgressionAnalysis"] is True


def test_example_manifest_is_cfdna_methylation() -> None:
    manifest = json.loads((_EXAMPLE_DIR / "project_Healthy_vs_AD_Stages.json").read_text())
    reg = manifest["regulatory"]
    assert reg["primary_modality"] == "methylation"
    assert reg["primary_analyte"] == "cfdna"
    assert manifest["progression_labels"] == ["AD_MCI", "AD_AD"]
