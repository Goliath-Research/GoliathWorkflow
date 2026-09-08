"""cfdna_emseq_mhl_survival procedure and mode overlay."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline_profiles import (
    apply_pipeline_procedure,
    apply_pipeline_profile,
    load_procedure,
    load_profile,
    seed_pipeline_scope_flags,
)

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"


def test_mhl_survival_procedure_loads() -> None:
    data = load_procedure("cfdna_emseq_mhl_survival")
    assert data["pipelineProcedure"] == "cfdna_emseq_mhl_survival"
    assert data["researchMode"] == "mhl_survival"
    assert data["analyteExpectation"] == "cfdna"
    assert "study_validation_mhl_survival.program.json" in str(data["lifecycleProgram"])
    ac = data["actionConfig"]
    assert ac["methyl_extract"]["mhap"]["enabled"] is True
    assert ac["parabricks"]["write_methylation_tags"] is True
    assert ac["mhb_mhl"]["mode"] == "discovery"
    assert ac["validation"]["backend_profiles"]["cox"]["enabled"] is True


def test_mhl_survival_mode_on_samd_research() -> None:
    ctx = apply_pipeline_profile(
        {"projectPath": "/tmp/project.json", "researchMode": "mhl_survival"},
        load_profile("samd_research"),
    )
    assert ctx["researchMode"] == "mhl_survival"
    validation = (ctx.get("actionConfig") or {}).get("validation") or {}
    assert validation.get("stability_early_stop_enabled") is True
    cox = (validation.get("backend_profiles") or {}).get("cox") or {}
    assert cox.get("enabled") is True


def test_mhl_survival_procedure_seed() -> None:
    ctx = apply_pipeline_procedure({}, load_procedure("cfdna_emseq_mhl_survival"))
    ctx = seed_pipeline_scope_flags(ctx, action_config=ctx.get("actionConfig"))
    assert ctx["libraryProtocol"] == "emseq_targeted"
    assert ctx["useEmseqTargeted"] is True


def test_lifecycle_program_exists() -> None:
    path = _DOMAIN / "fixtures" / "study_validation_mhl_survival.program.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    actions = [n.get("do") for n in body["body"]]
    assert "pipeline.mhb_mhl" in actions
    assert "validation.model_mc" in actions
    assert "pipeline.centroid" not in actions
