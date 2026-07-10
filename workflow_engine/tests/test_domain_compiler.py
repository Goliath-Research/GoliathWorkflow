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
    assert centroid_g1.input_template["projectPath"] == "${var.projectPath}"
    assert centroid_g1.input_template["outputDir"] == "${var.centroid1Dir}"

    detect = next(n for n in wf.nodes if n.node_key == "detect")
    assert detect.input_template["chromosome"] == "${var.chromosome}"
    assert detect.input_template["context"] == "${var.context}"
    assert detect.input_template["centroid1Dir"] == "${var.centroid1Dir}"
    assert detect.input_template["outputDir"] == "${var.detectOutDir}"
    assert detect.input_template["resolvedConfig"] == "${var.resolvedConfig__detection}"
    assert detect.input_template["hyperparamSetId"] == "${var.hyperparamSetId}"


def test_compiler_emits_root_scope_defaults():
    result = compile_domain_program(_load("two_group_comparison.program.json"))
    defaults = {d.var_name: d.node_key for d in result.workflow.scope_defaults}
    assert defaults.get("projectPath") == "root"
    assert defaults.get("centroid1Dir") == "root"


def test_compiler_preserves_iteration_dotted_refs_for_mc_gene_select():
    program_path = (
        Path(__file__).resolve().parents[1]
        / "domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json"
    )
    result = compile_domain_program_file(program_path, enrich_context=False)
    gene_select = next(n for n in result.workflow.nodes if n.node_key == "gene_select")
    assert gene_select.input_template["runDir"] == "${var.iteration.runDir}"
    assert gene_select.input_template["projectPath"] == "${var.iteration.projectPath}"


def test_compiler_emits_validation_scope_output_bindings():
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "ValidationBindings",
            "projectPath": "/work/project.json",
            "body": [
                {"do": "validation.plan_iterations", "node_key": "plan"},
                {"do": "validation.prepare_freeze_project", "node_key": "freeze"},
                {"do": "validation.select_best_model", "node_key": "select"},
            ],
        }
    )
    result = compile_domain_program(program)
    bindings = {(b.node_key, b.var_name, b.source_json_path) for b in result.workflow.output_bindings}
    assert ("plan", "iterations", "$.iterations") in bindings
    assert ("freeze", "fixedDmpPanel", "$.fixedDmpPanel") in bindings
    assert ("select", "selectedBackend", "$.selectedBackend") in bindings


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
        "projectPath": "/work/projects/prostate-cancer/configs/project_Healthy_vs_PCa.json"
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


def test_buffy_action_templates_are_self_contained_when_resolved():
    """Resolved scope should satisfy catalog required keys (parity check helper)."""
    check = Path(__file__).resolve().parents[1] / "domain" / "checks" / "buffy_healthy_vs_pca"
    program_path = check / "configs" / "buffy_data_driven.program.json"
    result = compile_domain_program_file(program_path, enrich_context=True)
    wf = result.workflow

    _DOMAIN = Path(__file__).resolve().parents[1] / "domain"
    if str(_DOMAIN) not in sys.path:
        sys.path.insert(0, str(_DOMAIN))
    from workflow_context import resolve_input_json_from_template, validate_resolved_input_json

    scope = {
        "projectPath": result.context_json["projectPath"],
        "centroid1Dir": result.context_json["centroid1Dir"],
        "centroid2Dir": "/work/out/centroid2",
        "detectOutDir": "/work/out/detect",
        "chromosome": "21",
        "context": "CG",
        "control_group": "all",
        "disease_group": "PCa",
        "label": "PCa",
    }
    for node in wf.nodes:
        if node.node_type != "ACTION" or not node.input_template or not node.action_name:
            continue
        resolved = resolve_input_json_from_template(node.input_template, scope)
        errors = validate_resolved_input_json(resolved, node.action_name)
        assert errors == [], f"{node.node_key}: {errors}"


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


def test_assign_while_pagination_compiles():
    result = compile_domain_program(_load("assign_while_pagination.program.json"))
    wf = result.workflow
    assert any(n.node_type == "WHILE" for n in wf.nodes)
    actions = [n.action_name for n in wf.nodes if n.node_type == "ACTION"]
    assert "workflow.const_bool" in actions
    assert "workflow.json_path_bool" in actions
    assert wf.variable_schemas["hasMore"] == "schemas/vars/bool.schema.json"
    bindings = {(b.var_name, b.source_json_path) for b in wf.output_bindings}
    assert ("hasMore", "$.value") in bindings


def test_assign_map_reduce_compiles():
    result = compile_domain_program(_load("assign_map_reduce.program.json"))
    wf = result.workflow
    assert any(n.node_type == "FOREACH" for n in wf.nodes)
    assert any(n.action_name == "workflow.fs_stat" for n in wf.nodes if n.node_type == "ACTION")
    assert result.context_json["artifactPaths"] == ["/work/cache/a.json", "/work/cache/b.json"]
    assert "summary" in wf.variable_schemas


def test_compile_switch_while_repeat():
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "ControlFlow",
            "projectPath": "/work/project.json",
            "variables": {
                "gate": {"schemaRef": "schemas/vars/int.schema.json"},
                "flag": {"schemaRef": "schemas/vars/bool.schema.json"},
            },
            "body": [
                {
                    "assign": "gate",
                    "using": "workflow.const_int",
                    "with": {"value": 1},
                    "node_key": "set_gate",
                },
                {
                    "switch": "${gate}",
                    "cases": {
                        "0": [{"do": "workflow.const_bool", "with": {"value": False}}],
                        "1": [{"do": "workflow.const_bool", "with": {"value": True}}],
                    },
                    "default": [{"do": "workflow.const_bool", "with": {"value": False}}],
                },
                {
                    "assign": "flag",
                    "using": "workflow.const_bool",
                    "with": {"value": True},
                },
                {"while": "${flag}", "do": [{"do": "workflow.const_int", "with": {"value": 0}}]},
                {"repeat": 2, "do": [{"do": "workflow.const_string", "with": {"value": "x"}}]},
            ],
        }
    )
    result = compile_domain_program(program)
    types = {n.node_type for n in result.workflow.nodes}
    assert {"SWITCH", "WHILE", "REPEAT", "ACTION"} <= types
    sw = next(n for n in result.workflow.nodes if n.node_type == "SWITCH")
    case_edges = [e for e in result.workflow.edges if e.parent_node_key == sw.node_key]
    assert any(e.switch_case_value == 0 for e in case_edges)
    assert any(e.switch_case_value == 1 for e in case_edges)
    assert any(e.is_default for e in case_edges)
    rp = next(n for n in result.workflow.nodes if n.node_type == "REPEAT")
    assert rp.repeat_count == 2


def test_assign_undeclared_target_rejected():
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "BadAssign",
            "projectPath": "/work/project.json",
            "body": [
                {"assign": "missing", "using": "workflow.const_bool", "with": {"value": True}},
            ],
        }
    )
    with pytest.raises(ValueError, match="not declared"):
        compile_domain_program(program)


def test_assign_unknown_action_rejected():
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "BadAction",
            "projectPath": "/work/project.json",
            "variables": {"x": {"schemaRef": "schemas/vars/bool.schema.json"}},
            "body": [
                {"assign": "x", "using": "workflow.no_such_action", "with": {"value": True}},
            ],
        }
    )
    with pytest.raises(ValueError, match="unknown action"):
        compile_domain_program(program)


def test_parallel_shared_assign_rejected():
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "ParallelAssign",
            "projectPath": "/work/project.json",
            "variables": {"flag": {"schemaRef": "schemas/vars/bool.schema.json"}},
            "body": [
                {
                    "parallel": [
                        {
                            "assign": "flag",
                            "using": "workflow.const_bool",
                            "with": {"value": True},
                        },
                        {
                            "assign": "flag",
                            "using": "workflow.const_bool",
                            "with": {"value": False},
                        },
                    ]
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="parallel"):
        compile_domain_program(program)


def test_assign_schema_plug_mismatch_rejected():
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "PlugMismatch",
            "projectPath": "/work/project.json",
            "variables": {"flag": {"schemaRef": "schemas/vars/int.schema.json"}},
            "body": [
                {
                    "assign": "flag",
                    "using": "workflow.const_bool",
                    "with": {"value": True},
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="incompatible"):
        compile_domain_program(program)


def test_assign_foreach_as_collision_rejected():
    program = DomainProgram.model_validate(
        {
            "programVersion": 2,
            "name": "ForeachCollision",
            "projectPath": "/work/project.json",
            "variables": {
                "paths": ["/a"],
                "item": {"schemaRef": "schemas/vars/string.schema.json"},
            },
            "body": [
                {
                    "for": {"in": {"ref": "paths"}, "as": "item", "parallel": False},
                    "do": [
                        {
                            "assign": "item",
                            "using": "workflow.const_string",
                            "with": {"value": "x"},
                        }
                    ],
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="collides with FOREACH"):
        compile_domain_program(program)
