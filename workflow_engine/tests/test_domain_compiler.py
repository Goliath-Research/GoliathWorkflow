"""Golden-style tests: DomainProgram IR lowers to SamplePrepPipeline-shaped graphs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from methyl_domain.program import DomainProgram

FIXTURES = Path(__file__).resolve().parents[1] / "domain" / "fixtures"
_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
_CONTRACT = Path(__file__).resolve().parents[1] / "contract"
_WORKERS = Path(__file__).resolve().parents[2] / "workers"
for _p in (_DOMAIN, _CONTRACT, _WORKERS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from compiler import compile_domain_program  # noqa: E402

SAMPLE_PREP_THEN_ACTIONS = [
    "sample.download_fastq",
    "sample.parabricks_fq2bam",
    "sample.delete_fastqs",
    "sample.methyl_qc",
    "sample.fragmentomics",
    "sample.methyl_extract",
    "sample.delete_bam",
]


def _load_sample_prep_program() -> DomainProgram:
    data = json.loads((FIXTURES / "sample_prep.program.json").read_text(encoding="utf-8"))
    return DomainProgram.model_validate(data)


def _action_sequence(workflow) -> list[str]:
    """Walk the happy path (THEN branches only) and collect ACTION names in order."""
    nodes_by_key = {n.node_key: n for n in workflow.nodes}
    edges_by_parent: dict[str, list] = {}
    for e in workflow.edges:
        edges_by_parent.setdefault(e.parent_node_key, []).append(e)
    for edges in edges_by_parent.values():
        edges.sort(key=lambda e: (e.branch_kind, e.child_order))

    actions: list[str] = []
    visited: set[str] = set()

    def walk(key: str) -> None:
        if key in visited:
            return
        visited.add(key)
        node = nodes_by_key.get(key)
        if node is None:
            return
        if node.node_type == "ACTION" and node.action_name:
            actions.append(node.action_name)
        for edge in edges_by_parent.get(key, []):
            if edge.branch_kind == "ELSE":
                continue
            if edge.branch_kind in ("SEQUENCE", "BODY", "THEN"):
                walk(edge.child_node_key)

    walk(workflow.root_node_key)
    return actions


def test_compile_sample_prep_action_sequence():
    program = _load_sample_prep_program()
    result = compile_domain_program(program)
    wf = result.workflow

    assert wf.name == "SamplePrepPipeline"
    assert _action_sequence(wf) == SAMPLE_PREP_THEN_ACTIONS

    qc_failed = next(n for n in wf.nodes if n.node_key == "qc_failed")
    assert qc_failed.action_name == "sample.qc_failed"
    if_qc = next(n for n in wf.nodes if n.node_type == "IF" and n.condition_var == "qcPass")
    assert any(
        e.parent_node_key == if_qc.node_key and e.branch_kind == "ELSE" for e in wf.edges
    )

    foreach_nodes = [n for n in wf.nodes if n.node_type == "FOREACH"]
    assert len(foreach_nodes) == 1
    assert foreach_nodes[0].foreach_collection_var == "samples"
    assert foreach_nodes[0].foreach_item_var == "sample"
    assert foreach_nodes[0].foreach_parallel is True

    if_nodes = [n for n in wf.nodes if n.node_type == "IF"]
    assert {n.condition_var for n in if_nodes} == {"qcPass", "isCfdna"}

    qc_bindings = [b for b in wf.output_bindings if b.var_name == "qcPass"]
    assert len(qc_bindings) == 1
    assert qc_bindings[0].source_json_path == "$.guardrails.overall_pass"

    methyl_qc = next(n for n in wf.nodes if n.node_key == "methyl_qc")
    assert methyl_qc.input_template.get("tool") == "MethylAlignmentQc"
    assert "${var.projectPath}" in str(methyl_qc.input_template.get("project"))


def test_compile_context_json_includes_program_variables():
    program = _load_sample_prep_program()
    result = compile_domain_program(program)
    assert result.context_json["primaryAnalyte"] == "cfdna"
    assert "projectPath" in result.context_json
