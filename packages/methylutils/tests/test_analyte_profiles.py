"""Tests for analyte-driven step_config profiles."""

from methyl_utils.analyte_profiles import (
    cisbp_mode_label,
    merge_step_config,
    normalize_primary_analyte,
    profile_for_analyte,
    resolve_cisbp_modes,
    should_apply_analyte_profile,
)
from methyl_utils.pipeline_config import ProjectConfig, load_project


def test_normalize_primary_analyte():
    assert normalize_primary_analyte("Plasma cfDNA") == "cfdna"
    assert normalize_primary_analyte("buffy") == "buffy_coat"


def test_cfdna_profile_fills_missing_keys():
    user = {"genome_fasta": "/custom.fa"}
    merged = merge_step_config("alignment_qc", user, "cfdna")
    assert merged["genome_fasta"] == "/custom.fa"
    assert merged["auto_profile_from_analyte"] is True
    assert merged["fragmentomics"]["profile"] == "cfdna"
    assert merged["bisulfite_conversion"]["enabled"] is True
    assert merged["alignment_guardrails"]["enabled"] is True
    assert merged["alignment_guardrails"]["min_mapping_rate"] == 0.98


def test_buffy_profile_enables_alignment_guardrails():
    merged = merge_step_config("alignment_qc", {}, "buffy_coat")
    assert merged["alignment_guardrails"]["enabled"] is True
    assert merged["alignment_guardrails"]["flagstat_enabled"] is True


def test_user_override_wins_over_profile():
    user = {"fragmentomics": {"enabled": False}}
    merged = merge_step_config("alignment_qc", user, "cfdna")
    assert merged["fragmentomics"]["enabled"] is False


def test_buffy_disables_fragmentomics_step():
    merged = merge_step_config("fragmentomics", {}, "buffy_coat")
    assert merged["enabled"] is False


def test_should_apply_opt_out():
    assert should_apply_analyte_profile({"primary_analyte": "cfdna"}) is True
    assert should_apply_analyte_profile(
        {"primary_analyte": "cfdna", "auto_apply_analyte_profile": False}
    ) is False


def test_resolve_action_config_applies_analyte_profile():
    from methyl_utils.action_config_resolver import resolve_action_config

    cfg = resolve_action_config(
        "alignment_qc",
        profile_action_config={},
        regulatory={"primary_analyte": "cfdna"},
    )
    assert cfg["auto_profile_from_analyte"] is True
    frag = resolve_action_config(
        "fragmentomics",
        profile_action_config={},
        regulatory={"primary_analyte": "cfdna"},
    )
    assert frag["enabled"] is True
    enr = resolve_action_config(
        "enricher",
        profile_action_config={},
        regulatory={"primary_analyte": "cfdna"},
    )
    assert enr["cisbp"]["enabled"] is True
    assert enr["cisbp"]["cisbp_modes"] == ["gene_sets", "motif_scan", "annotate"]


def test_cisbp_mode_label_and_resolve():
    assert cisbp_mode_label("gene_sets") == "CIS-BP"
    assert cisbp_mode_label("motif_scan") == "CIS-BP-motif"

    class _Cfg:
        cisbp_modes = ["annotate", "gene_sets", "motif_scan"]
        mode = "gene_sets"

    assert resolve_cisbp_modes(_Cfg()) == ["gene_sets", "motif_scan", "annotate"]
