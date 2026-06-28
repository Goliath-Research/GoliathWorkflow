"""Tests for statistical DMP/gene modeling mode profiles (fixture-only)."""

from __future__ import annotations

from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(DOMAIN) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(DOMAIN))

from pipeline_profiles import apply_pipeline_profile, load_profile  # noqa: E402


@pytest.mark.parametrize(
    ("profile_name", "dmp_mode", "gene_mode", "run_dmp", "run_gene_fc"),
    [
        ("mc_dmp_discovery", "raw_pool", "none", False, False),
        ("mc_dmp_featurecuts", "featurecuts", "none", True, False),
        ("mc_gene_mapper", "raw_pool", "mapper_ranked", False, False),
        ("mc_gene_featurecuts", "raw_pool", "featurecuts", False, True),
        ("phase_a_dmp_stability", "featurecuts", "none", True, False),
        ("phase_b_gene_from_stable_dmps", "stable_panel", "from_stable_dmp_panel", False, True),
    ],
)
def test_statistical_profile_presets(
    profile_name: str,
    dmp_mode: str,
    gene_mode: str,
    run_dmp: bool,
    run_gene_fc: bool,
) -> None:
    profile = load_profile(profile_name)
    ctx = apply_pipeline_profile({"projectPath": "/tmp/project.json"}, profile)
    assert ctx.get("dmp_modeling_mode") == dmp_mode or profile.get("dmp_modeling_mode") == dmp_mode
    assert ctx.get("gene_modeling_mode") == gene_mode or profile.get("gene_modeling_mode") == gene_mode
    assert ctx["runDmpSelection"] is run_dmp
    assert ctx["runGeneFeaturecuts"] is run_gene_fc
    validation = (ctx.get("actionConfig") or {}).get("validation") or {}
    if dmp_mode == "featurecuts":
        assert validation.get("dmp_featurecuts_target_ba") == 0.95 or validation.get(
            "stability_target_balanced_accuracy"
        )


def test_phase_b_wires_stable_dmp_csv_from_context() -> None:
    stable = "/work/artifacts/stability/stable_dmps_production.csv"
    profile = load_profile("phase_b_gene_from_stable_dmps")
    ctx = apply_pipeline_profile(
        {
            "projectPath": "/tmp/project.json",
            "stableDmpCsv": stable,
        },
        profile,
    )
    validation = (ctx.get("actionConfig") or {}).get("validation") or {}
    assert validation.get("freeze_stable_dmp_csv") == stable
    assert validation.get("gene_featurecuts_loci_source") == "stable_panel"
    mapper = (ctx.get("actionConfig") or {}).get("mapper") or {}
    assert "stable_dmps" in str(mapper.get("csv_pattern", ""))


def test_deprecated_profile_aliases_resolve() -> None:
    assert load_profile("gene_enricher_stability")["pipelineProfile"] == "mc_dmp_discovery"
    assert load_profile("dmp_panel_stability")["pipelineProfile"] == "mc_dmp_featurecuts"
