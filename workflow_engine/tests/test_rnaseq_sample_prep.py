"""RNA-Seq process pack: program compile + profile quant-mode resolution checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))

from compiler import compile_domain_program_file  # noqa: E402

_FIXTURES = Path(__file__).resolve().parents[1] / "domain" / "fixtures"


def _load(name: str):
    return json.loads((_FIXTURES / name).read_text())


def test_rnaseq_sample_prep_compiles_with_quant_branch() -> None:
    result = compile_domain_program_file(
        _FIXTURES / "sample_prep_rnaseq.program.json", enrich_context=False
    )
    action_names = [n.action_name for n in result.workflow.nodes if n.node_type == "ACTION"]
    assert "sample.parabricks_rna_fq2bam" in action_names
    assert "sample.kallisto" in action_names
    assert "sample.rna_qc" in action_names
    assert "sample.register_expression" in action_names


def test_rnaseq_study_lifecycle_compiles() -> None:
    result = compile_domain_program_file(
        _FIXTURES / "rnaseq_study_lifecycle.program.json", enrich_context=False
    )
    action_names = [n.action_name for n in result.workflow.nodes if n.node_type == "ACTION"]
    assert "pipeline.rna_de_select" in action_names


def test_pipeline_profiles_seed_use_kallisto_from_quant_mode() -> None:
    from pipeline_profiles import seed_pipeline_scope_flags

    star = seed_pipeline_scope_flags(
        {"pipelineProfile": "rnaseq_research"},
        action_config={"rna_align": {"quant_mode": "star"}},
    )
    assert star["quantMode"] == "star"
    assert star["useKallisto"] is False

    kallisto = seed_pipeline_scope_flags(
        {"pipelineProfile": "rnaseq_research"},
        action_config={"rna_align": {"quant_mode": "kallisto"}},
    )
    assert kallisto["quantMode"] == "kallisto"
    assert kallisto["useKallisto"] is True


def test_rnaseq_prep_qc_gate_present() -> None:
    program = _load("sample_prep_rnaseq.program.json")
    assert "qcPass" in program["variables"]
    assert "useKallisto" in program["variables"]
    text = json.dumps(program)
    assert '"${qcPass}"' in text
    assert '"${useKallisto}"' in text
