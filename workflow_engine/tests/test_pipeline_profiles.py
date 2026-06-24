"""Tests for composable pipeline profile presets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(DOMAIN) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(DOMAIN))

from compiler import compile_domain_program_file  # noqa: E402
from pipeline_profiles import (  # noqa: E402
    apply_pipeline_profile,
    load_profile,
    seed_pipeline_scope_flags,
)
from workflow_context import enrich_instance_context  # noqa: E402


def test_gene_enricher_stability_profile_flags() -> None:
    profile = load_profile("gene_enricher_stability")
    ctx = apply_pipeline_profile({"projectPath": "/tmp/project.json"}, profile)
    assert ctx["runDmpSelection"] is False
    assert ctx["stabilityFeaturecutsEnabled"] is False
    assert ctx["stabilityGeneFeaturecutsEnabled"] is False


def test_full_biomarker_profile_enables_optional_branches() -> None:
    ctx = apply_pipeline_profile({}, load_profile("full_biomarker_gene_fc"))
    assert ctx["runDmpSelection"] is True
    assert ctx["runGeneFeaturecuts"] is True
    assert ctx["runBiomarkerFilter"] is True


def test_enrich_instance_context_seeds_flags_from_validation() -> None:
    ctx = enrich_instance_context(
        {
            "projectPath": str(
                DOMAIN / "checks/buffy_healthy_vs_pca/configs/project_Buffy_healthy_vs_PCa.json"
            ),
            "pipelineProfile": "gene_enricher_stability",
        }
    )
    assert "runDmpSelection" in ctx
    assert ctx["runDmpSelection"] is False


@pytest.mark.parametrize(
    "program_path",
    [
        DOMAIN / "checks/pca1_5_cg/configs/pca1_5_mc_stability.program.json",
        DOMAIN / "checks/pca1_5_cg/configs/mc_gene_enricher_stability.program.json",
        DOMAIN / "checks/buffy_healthy_vs_pca/configs/buffy_interpretation.program.json",
        DOMAIN / "fixtures/dmp_select_optional.program.json",
    ],
)
def test_composable_programs_compile_with_if_nodes(program_path: Path) -> None:
    project = DOMAIN / "checks/buffy_healthy_vs_pca/configs/project_Buffy_healthy_vs_PCa.json"
    if "pca1_5" in str(program_path):
        project = DOMAIN / "checks/pca1_5_cg/configs/project_Healthy_vs_PCa1-5-CG_smoke.json"
    result = compile_domain_program_file(program_path, enrich_context=False)
    ctx = enrich_instance_context(
        {
            "projectPath": str(project),
            "pipelineProfile": "full_biomarker_gene_fc",
        }
    )
    merged = {**result.context_json, **ctx}
    spec = result.workflow
    node_types = {n.node_type for n in spec.nodes}
    if "dmp_select_optional" in program_path.name or "mc_stability" in program_path.name:
        assert "IF" in node_types
    assert any(n.action_name == "pipeline.detector" for n in spec.nodes if n.action_name)


def test_mc_gene_enricher_program_has_enricher_not_dmp_select() -> None:
    program = DOMAIN / "checks/pca1_5_cg/configs/mc_gene_enricher_stability.program.json"
    raw = json.loads(program.read_text(encoding="utf-8"))
    body = json.dumps(raw["body"])
    assert "pipeline.enricher" in body
    assert "pipeline.dmp_select" not in body
    assert "pipeline.gene_select" not in body
