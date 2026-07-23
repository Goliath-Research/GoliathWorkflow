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
    _deep_merge,
    apply_pipeline_profile,
    load_profile,
    seed_pipeline_scope_flags,
)
from workflow_context import enrich_instance_context  # noqa: E402


# --------------------------------------------------------------------------- #
# _deep_merge (pure dict logic, tier-1 runnable)
# --------------------------------------------------------------------------- #
def test_deep_merge_recurses_and_overlay_wins() -> None:
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    overlay = {"a": 2, "nested": {"y": 20, "z": 30}}
    assert _deep_merge(base, overlay) == {
        "a": 2,
        "nested": {"x": 1, "y": 20, "z": 30},
    }


def test_deep_merge_scalar_replaces_dict() -> None:
    assert _deep_merge({"k": {"a": 1}}, {"k": 5})["k"] == 5


# --------------------------------------------------------------------------- #
# apply_pipeline_profile action config + flag merge precedence
# --------------------------------------------------------------------------- #
def test_apply_pipeline_profile_merges_action_config() -> None:
    ctx = {"actionConfig": {"detection": {"alpha": 0.05, "min_coverage": 4}}}
    profile = {
        "pipelineProfile": "custom",
        "actionConfig": {"detection": {"alpha": 0.01}},
    }
    out = apply_pipeline_profile(ctx, profile)
    # Instance/context actionConfig wins on the shared key; profile-only keys survive.
    assert out["actionConfig"]["detection"]["alpha"] == 0.05
    assert out["actionConfig"]["detection"]["min_coverage"] == 4
    assert out["pipelineProfile"] == "custom"


def test_context_null_clears_profile_stability_min_balanced_accuracy() -> None:
    """Explicit JSON null in context must unset a profile science knob."""
    profile = load_profile("full_biomarker_gene_fc")
    assert (profile.get("actionConfig") or {}).get("validation", {}).get(
        "stability_min_balanced_accuracy"
    ) == 0.95
    out = apply_pipeline_profile(
        {
            "pipelineProfile": "full_biomarker_gene_fc",
            "actionConfig": {
                "validation": {"stability_min_balanced_accuracy": None},
            },
        },
        profile,
    )
    validation = (out.get("actionConfig") or {}).get("validation") or {}
    assert validation.get("stability_min_balanced_accuracy") is None
    assert out.get("runDmpSelection") is True


def test_apply_pipeline_profile_sets_flags_from_preset() -> None:
    out = apply_pipeline_profile({}, load_profile("full_biomarker_gene_fc"))
    assert out["runDmpSelection"] is True
    assert out["runBiomarkerFilter"] is True


def test_apply_pipeline_profile_explicit_profile_flag_overrides_preset() -> None:
    # Preset for mc_dmp_gene_fc sets runDmpSelection True; explicit False in the
    # profile body must win.
    profile = {"pipelineProfile": "mc_dmp_gene_fc", "runDmpSelection": False}
    out = apply_pipeline_profile({}, profile)
    assert out["runDmpSelection"] is False


def test_research_profile_presets() -> None:
    mc_dmp = apply_pipeline_profile({}, load_profile("mc_dmp"))
    assert mc_dmp["runDmpSelection"] is False
    assert mc_dmp["runGeneFeaturecuts"] is False
    assert mc_dmp["researchMode"] == "dmp_raw"

    mc_dmp_fc = apply_pipeline_profile({}, load_profile("mc_dmp_fc"))
    assert mc_dmp_fc["runDmpSelection"] is True
    assert mc_dmp_fc["runGeneFeaturecuts"] is False
    assert mc_dmp_fc["researchMode"] == "dmp_fc"

    mc_gene = apply_pipeline_profile({}, load_profile("mc_gene"))
    assert mc_gene["runDmpSelection"] is False
    assert mc_gene["runGeneFeaturecuts"] is False
    assert mc_gene["researchMode"] == "gene_enricher"

    mc_gene_fc = apply_pipeline_profile({}, load_profile("mc_gene_fc"))
    assert mc_gene_fc["runDmpSelection"] is False
    assert mc_gene_fc["runGeneFeaturecuts"] is True
    assert mc_gene_fc["researchMode"] == "gene_fc"

    mc_dmp_gene_fc = apply_pipeline_profile({}, load_profile("mc_dmp_gene_fc"))
    assert mc_dmp_gene_fc["runDmpSelection"] is True
    assert mc_dmp_gene_fc["runGeneFeaturecuts"] is True
    assert mc_dmp_gene_fc["researchMode"] == "dual_fc"

    samd = apply_pipeline_profile({}, load_profile("samd_research"))
    assert samd["runDmpSelection"] is True
    assert samd["runGeneFeaturecuts"] is True
    assert samd["researchMode"] == "dual_fc"


def test_gene_enricher_stability_profile_flags() -> None:
    profile = load_profile("gene_enricher_stability")
    ctx = apply_pipeline_profile({"projectPath": "/tmp/project.json"}, profile)
    assert ctx["runDmpSelection"] is False
    assert ctx["stabilityFeaturecutsEnabled"] is False
    assert ctx["stabilityGeneFeaturecutsEnabled"] is False


def test_discovery_gene_featurecuts_profile() -> None:
    profile = load_profile("discovery_gene_featurecuts")
    ctx = apply_pipeline_profile({"projectPath": "/tmp/project.json"}, profile)
    assert ctx["runDmpSelection"] is True
    assert ctx["runGeneFeaturecuts"] is True
    assert ctx["runBiomarkerFilter"] is False
    overrides = ctx.get("actionConfig") or {}
    assert overrides.get("mapper", {}).get("csv_pattern") == "dmps-*-discovery.csv"


def test_full_biomarker_profile_enables_optional_branches() -> None:
    ctx = apply_pipeline_profile({}, load_profile("full_biomarker_gene_fc"))
    assert ctx["runDmpSelection"] is True
    assert ctx["runGeneFeaturecuts"] is True
    assert ctx["runBiomarkerFilter"] is True


def test_enrich_instance_context_seeds_flags_from_validation(local_project) -> None:
    project = local_project(
        DOMAIN / "checks/buffy_healthy_vs_pca/configs/project_Buffy_healthy_vs_PCa.json"
    )
    ctx = enrich_instance_context(
        {
            "projectPath": str(project),
            "pipelineProfile": "gene_enricher_stability",
        }
    )
    assert "runDmpSelection" in ctx
    assert ctx["runDmpSelection"] is False


def test_enrich_preserves_profile_validation_when_single_pipeline_flag_set(local_project) -> None:
    """Regression: one PIPELINE_FLAG in context must not drop profile actionConfig for other flags."""
    project = local_project(DOMAIN / "checks/pca1_5_cg/configs/project_Healthy_vs_PCa1-5-CG.json")
    ctx = enrich_instance_context(
        {
            "projectPath": str(project),
            "runDmpSelection": True,
            "pipelineProfile": "staged_ovr_mc",
        }
    )
    assert ctx["runDmpSelection"] is True
    assert ctx["stabilityFeaturecutsEnabled"] is True


@pytest.mark.parametrize(
    "program_path",
    [
        DOMAIN / "fixtures/mc_stability_staged.program.json",
        DOMAIN / "fixtures/mc_gene_enricher_stability.program.json",
        DOMAIN / "fixtures/interpretation.program.json",
        DOMAIN / "fixtures/dmp_select_optional.program.json",
    ],
)
def test_composable_programs_compile_with_if_nodes(program_path: Path, local_project) -> None:
    src_project = DOMAIN / "checks/buffy_healthy_vs_pca/configs/project_Buffy_healthy_vs_PCa.json"
    if "staged" in program_path.name or "gene_enricher" in program_path.name:
        src_project = DOMAIN / "checks/pca1_5_cg/configs/project_Healthy_vs_PCa1-5-CG_smoke.json"
    project = local_project(src_project)
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
    program = DOMAIN / "fixtures/mc_gene_enricher_stability.program.json"
    raw = json.loads(program.read_text(encoding="utf-8"))
    body = json.dumps(raw["body"])
    assert "pipeline.enricher" in body
    assert "pipeline.dmp_select" not in body
    assert "pipeline.gene_select" not in body
