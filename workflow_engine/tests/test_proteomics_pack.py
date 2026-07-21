"""Proteomics pack: program compile + profile ingest-mode resolution + modality checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DOMAIN = _REPO / "workflow_engine" / "domain"
for _p in (str(_DOMAIN), str(_REPO / "packages" / "methylutils")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from compiler import compile_domain_program_file  # noqa: E402

_FIXTURES = _DOMAIN / "fixtures"


def test_sample_prep_proteomics_compiles_with_ingest_branches() -> None:
    result = compile_domain_program_file(
        _FIXTURES / "sample_prep_proteomics.program.json", enrich_context=False
    )
    action_names = [n.action_name for n in result.workflow.nodes if n.node_type == "ACTION"]
    assert "sample.ingest_panel" in action_names
    assert "sample.diann" in action_names
    assert "sample.dl_rescore" in action_names
    assert "sample.register_abundance" in action_names
    assert "sample.proteomics_qc" in action_names


def test_proteomics_study_lifecycle_compiles() -> None:
    result = compile_domain_program_file(
        _FIXTURES / "proteomics_study_lifecycle.program.json", enrich_context=False
    )
    action_names = [n.action_name for n in result.workflow.nodes if n.node_type == "ACTION"]
    assert "pipeline.protein_de_select" in action_names


def test_profile_resolves_ingest_mode_flags() -> None:
    from pipeline_profiles import seed_pipeline_scope_flags

    dia = seed_pipeline_scope_flags(
        {"pipelineProfile": "proteomics_research"},
        action_config={"proteomics_quant": {"ingest_mode": "dia"}},
    )
    assert dia["usePanel"] is False and dia["ingestMode"] == "dia"

    panel = seed_pipeline_scope_flags(
        {"pipelineProfile": "proteomics_research"},
        action_config={"proteomics_quant": {"ingest_mode": "panel", "rescore": True}},
    )
    assert panel["usePanel"] is True
    assert panel["useRescore"] is True


def test_proteomics_modality_normalizes() -> None:
    from methyl_utils.analyte_profiles import normalize_primary_modality

    assert normalize_primary_modality("proteomics") == "proteomics"
    assert normalize_primary_modality("mass spec") == "proteomics"


def test_proteomics_feature_mode_accepted() -> None:
    import pytest
    from methyl_validation.config import BackendSharedParams  # type: ignore

    cfg = BackendSharedParams(feature_mode="proteomics_abundance")
    assert cfg.feature_mode == "proteomics_abundance"
    with pytest.raises(Exception):
        BackendSharedParams(feature_mode="not_a_mode")
