"""Tests for analyte-driven step_config profiles."""

from methyl_utils.analyte_profiles import (
    cisbp_mode_label,
    merge_step_config,
    normalize_primary_analyte,
    profile_for_analyte,
    resolve_cisbp_modes,
    should_apply_analyte_profile,
)
from methyl_utils.pipeline_config import ProjectConfig


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


def test_project_get_step_config_applies_profile():
    cfg = ProjectConfig.model_validate(
        {
            "project_name": "p",
            "output_base": "/out",
            "group1": {"label": "g1", "sample_paths": ["/s1"]},
            "group2": {"label": "g2", "sample_paths": ["/s2"]},
            "step_config": {
                "validation": {
                    "regulatory": {"primary_analyte": "cfdna"},
                },
            },
        }
    )
    aq = cfg.get_step_config("alignment_qc")
    assert aq["auto_profile_from_analyte"] is True
    assert cfg.get_step_config("fragmentomics")["enabled"] is True
    enr = cfg.get_step_config("enricher")
    assert enr["cisbp"]["enabled"] is True
    assert enr["cisbp"]["cisbp_modes"] == ["gene_sets", "motif_scan", "annotate"]


def test_cisbp_mode_label_and_resolve():
    assert cisbp_mode_label("gene_sets") == "CIS-BP"
    assert cisbp_mode_label("motif_scan") == "CIS-BP-motif"

    class _Cfg:
        cisbp_modes = ["annotate", "gene_sets", "motif_scan"]
        mode = "gene_sets"

    assert resolve_cisbp_modes(_Cfg()) == ["gene_sets", "motif_scan", "annotate"]
