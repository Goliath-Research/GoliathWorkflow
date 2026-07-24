"""Assay procedure pack loading, merge precedence, and analyte validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_DOMAIN = _REPO / "workflow_engine" / "domain"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))

from pipeline_profiles import (  # noqa: E402
    apply_pipeline_procedure,
    apply_pipeline_profile,
    load_procedure,
    load_profile,
    seed_pipeline_scope_flags,
    validate_procedure_analyte,
)

_PROCEDURES = _DOMAIN / "profiles" / "procedures"
_FIXTURES = _DOMAIN / "fixtures"


@pytest.mark.parametrize(
    "proc_id",
    [
        "buffy_wgbs_pangenome_gene_fc",
        "buffy_wgbs_linear_gene_fc",
        "cfdna_wgbs_plasma",
        "cfdna_emseq_targeted",
        "plant_wgbs_gene_fc",
    ],
)
def test_procedure_files_load(proc_id: str) -> None:
    data = load_procedure(proc_id)
    assert data["pipelineProcedure"] == proc_id
    assert data.get("pipelineProfile") == "samd_research"
    assert data.get("researchMode") == "gene_fc"
    assert ( _PROCEDURES / f"{proc_id}.procedure.json").is_file()


def test_buffy_pangenome_procedure_flags() -> None:
    ctx = apply_pipeline_procedure({}, load_procedure("buffy_wgbs_pangenome_gene_fc"))
    ctx = apply_pipeline_profile(ctx, load_profile(ctx["pipelineProfile"]))
    ctx = seed_pipeline_scope_flags(ctx, action_config=ctx.get("actionConfig"))
    assert ctx["pipelineProcedure"] == "buffy_wgbs_pangenome_gene_fc"
    assert ctx["researchMode"] == "gene_fc"
    assert ctx["libraryProtocol"] == "wgbs_pangenome"
    assert ctx["alignmentMode"] == "pangenome_wgbs"
    assert ctx["usePangenome"] is True
    assert ctx["useWgbsPangenome"] is True
    assert ctx["runGeneFeaturecuts"] is True
    assert ctx["runDmpSelection"] is False
    assert (ctx.get("actionConfig") or {}).get("cell_deconvolution", {}).get("method") == "houseman"
    assert "study_validation_lifecycle.program.json" in str(ctx.get("lifecycleProgram"))


def test_cfdna_plasma_clears_deconv_and_pins_lifecycle() -> None:
    ctx = apply_pipeline_procedure({}, load_procedure("cfdna_wgbs_plasma"))
    ctx = apply_pipeline_profile(ctx, load_profile(ctx["pipelineProfile"]))
    assert ctx["libraryProtocol"] == "wgbs_linear"
    assert ctx["usePangenome"] is False
    assert "no_deconv" in str(ctx.get("lifecycleProgram"))
    # Procedure null clears profile cell_deconvolution
    assert "cell_deconvolution" not in (ctx.get("actionConfig") or {})
    cov_paths = (
        ((ctx.get("actionConfig") or {}).get("validation") or {})
        .get("backend_profiles", {})
        .get("ecdf", {})
        .get("params", {})
        .get("covariates_path")
    )
    assert isinstance(cov_paths, list)
    assert not any("cell_fractions" in str(p) for p in cov_paths)


def test_emseq_procedure_protocol_and_program() -> None:
    ctx = apply_pipeline_procedure({}, load_procedure("cfdna_emseq_targeted"))
    ctx = seed_pipeline_scope_flags(ctx, action_config=ctx.get("actionConfig"))
    assert ctx["libraryProtocol"] == "emseq_targeted"
    assert ctx["useEmseqTargeted"] is True
    assert ctx["useEpiGbs"] is False
    assert "sample_prep_emseq.program.json" in str(ctx.get("samplePrepProgram"))
    me = (ctx.get("actionConfig") or {}).get("methyl_extract") or {}
    assert me.get("min_cov") == 20


def test_instance_overlay_wins_over_procedure() -> None:
    ctx = {
        "researchMode": "dual_fc",
        "actionConfig": {
            "cell_deconvolution": {"method": "hitimed"},
            "validation": {"gene_featurecuts_target_ba": 0.99},
        },
    }
    ctx = apply_pipeline_procedure(ctx, load_procedure("buffy_wgbs_linear_gene_fc"))
    assert ctx["researchMode"] == "dual_fc"
    assert ctx["actionConfig"]["cell_deconvolution"]["method"] == "hitimed"
    assert ctx["actionConfig"]["validation"]["gene_featurecuts_target_ba"] == 0.99


def test_validate_procedure_analyte_ok_and_mismatch() -> None:
    ok = {
        "pipelineProcedure": "buffy_wgbs_pangenome_gene_fc",
        "analyteExpectation": "buffy_coat",
        "regulatory": {"primary_analyte": "buffy_coat"},
    }
    validate_procedure_analyte(ok)

    bad = {
        "pipelineProcedure": "buffy_wgbs_pangenome_gene_fc",
        "analyteExpectation": "buffy_coat",
        "regulatory": {"primary_analyte": "cfdna"},
    }
    with pytest.raises(ValueError, match="buffy_coat"):
        validate_procedure_analyte(bad)


def test_no_deconv_lifecycle_omits_cell_deconvolution() -> None:
    prog = json.loads(
        (_FIXTURES / "study_validation_lifecycle_no_deconv.program.json").read_text()
    )
    do_actions = [n.get("do") for n in prog["body"] if isinstance(n, dict) and "do" in n]
    assert "pipeline.cell_deconvolution" not in do_actions
    assert "pipeline.info_measures" in do_actions
    assert "pipeline.mapper" in do_actions


def test_emseq_sample_prep_is_linear_parabricks() -> None:
    prog = json.loads((_FIXTURES / "sample_prep_emseq.program.json").read_text())
    text = json.dumps(prog)
    assert "sample.parabricks_fq2bam" in text
    assert "sample.parabricks_giraffe" not in text
    assert "sample.docker_align" not in text
    assert "${usePangenome}" not in text
