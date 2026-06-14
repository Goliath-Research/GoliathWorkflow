"""Tests for collection bindings and two-group program compilation."""

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

from compiler import compile_domain_program, compile_domain_program_file  # noqa: E402


def _load(name: str) -> DomainProgram:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return DomainProgram.model_validate(data)


def _node_keys_by_type(workflow, node_type: str) -> list[str]:
    return [n.node_key for n in workflow.nodes if n.node_type == node_type]


def test_two_group_compiles_nested_foreach_and_parallel():
    result = compile_domain_program(_load("two_group_comparison.program.json"))
    wf = result.workflow

    foreach_nodes = [n for n in wf.nodes if n.node_type == "FOREACH"]
    assert len(foreach_nodes) == 3
    collections = {n.foreach_collection_var for n in foreach_nodes}
    assert collections == {"comparisons", "contexts", "chromosomes"}
    assert all(n.foreach_parallel for n in foreach_nodes)

    parallel_nodes = [n for n in wf.nodes if n.node_type == "PARALLEL"]
    assert len(parallel_nodes) >= 1

    action_names = [
        n.action_name for n in wf.nodes if n.node_type == "ACTION" and n.action_name
    ]
    assert action_names.count("pipeline.centroid") == 2
    assert action_names.count("pipeline.detector") == 1

    centroid_g1 = next(n for n in wf.nodes if n.node_key == "centroid_g1")
    assert centroid_g1.input_template["chromosome"] == "${var.chromosome}"
    assert centroid_g1.input_template["context"] == "${var.context}"
    assert centroid_g1.input_template["group"] == "${var.control_group}"

    detect = next(n for n in wf.nodes if n.node_key == "detect")
    assert detect.input_template["chromosome"] == "${var.chromosome}"
    assert detect.input_template["context"] == "${var.context}"


def test_two_group_emits_collection_bindings():
    result = compile_domain_program(_load("two_group_comparison.program.json"))
    kinds = {b.scope_var: b.kind for b in result.workflow.collection_bindings}

    assert kinds["project"] == "jsonFile"
    assert kinds["chromosomes"] == "jsonPath"
    assert kinds["contexts"] == "jsonPath"
    assert kinds["comparisons"] == "jsonPath"

    chrom = next(b for b in result.workflow.collection_bindings if b.scope_var == "chromosomes")
    assert chrom.base_var == "project"
    assert chrom.json_path == "$.chromosomes"


def test_two_group_context_json_minimal():
    result = compile_domain_program(_load("two_group_comparison.program.json"))
    assert result.context_json == {
        "projectPath": "/work/prostate-cancer/configs/project_Healthy_vs_PCa.json"
    }


def test_parallel_block_edges_use_parallel_branch():
    """Direct children of a PARALLEL node must all link with branch_kind PARALLEL."""
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "ParallelBranchKinds",
            "projectPath": "/work/project.json",
            "body": [
                {
                    "parallel": [
                        {"do": "pipeline.centroid", "node_key": "centroid_a"},
                        {"do": "pipeline.centroid", "node_key": "centroid_b"},
                    ]
                }
            ],
        }
    )
    result = compile_domain_program(program)
    par_nodes = [n.node_key for n in result.workflow.nodes if n.node_type == "PARALLEL"]
    assert len(par_nodes) == 1
    par_key = par_nodes[0]
    child_edges = [
        e
        for e in result.workflow.edges
        if e.parent_node_key == par_key
        and e.child_node_key in ("centroid_a", "centroid_b")
    ]
    assert len(child_edges) == 2
    assert all(e.branch_kind == "PARALLEL" for e in child_edges)


def test_sample_prep_still_compiles():
    result = compile_domain_program(_load("sample_prep.program.json"))
    wf = result.workflow
    assert wf.name == "SamplePrepPipeline"
    assert any(n.node_type == "FOREACH" for n in wf.nodes)


def test_buffy_check_bundle_compiles_full_pipeline():
    check = Path(__file__).resolve().parents[1] / "domain" / "checks" / "buffy_healthy_vs_pca"
    program_path = check / "configs" / "buffy_data_driven.program.json"
    result = compile_domain_program_file(program_path)
    wf = result.workflow

    assert wf.name == "BuffyHealthyVsPCa"
    action_names = [n.action_name for n in wf.nodes if n.node_type == "ACTION"]
    assert action_names.count("pipeline.centroid") == 2
    assert "pipeline.detector" in action_names
    assert "pipeline.mapper" in action_names
    assert "pipeline.enricher" in action_names

    binding_vars = {b.scope_var for b in wf.collection_bindings}
    assert binding_vars >= {"project", "chromosomes", "contexts", "comparisons"}
    assert result.context_json["projectPath"].endswith("project_Buffy_healthy_vs_PCa.json")
