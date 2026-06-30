#!/usr/bin/env python3
"""Unit tests for FOREACH iteration scope flattening and template embedding."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_WORKERS = _ROOT / "workers"
if str(_WORKERS) not in sys.path:
    sys.path.insert(0, str(_WORKERS))


def json_fragment(value: object) -> str:
    """Encode as stored in wf.scope_variable.value_json."""
    return json.dumps(value, separators=(",", ":"))


def flatten_foreach_element(
    element: dict,
    *,
    item_var: str = "iteration",
    index_var: str = "iterIndex",
    index: int = 0,
) -> dict[str, str]:
    """Mirror wf_seed_foreach_iteration_scope object flattening (simplified)."""
    scope: dict[str, str] = {
        item_var: json_fragment(element),
        index_var: json_fragment(index),
    }
    for key, value in element.items():
        if key not in (item_var, index_var):
            scope[key] = json_fragment(value)
    return scope


def resolve_template(template: str, scope: dict[str, str]) -> str:
    """Resolve ${var.name} placeholders with JSON fragments from scope."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in scope:
            raise KeyError(name)
        return scope[name]

    resolved = re.sub(r"\$\{var\.([^}]+)\}", repl, template)
    return resolved


class ForeachIterationScopeTests(unittest.TestCase):
    def test_flatten_exposes_task_config_for_template(self) -> None:
        iteration = {
            "runId": "feature_run_0001",
            "phase": "feature",
            "projectPath": "/work/run_0001",
            "taskConfig": {
                "runId": "feature_run_0001",
                "phase": "feature",
                "iteration": 1,
                "trainFraction": 0.8,
            },
        }
        scope = flatten_foreach_element(iteration, index=0)
        template = (
            '{"tool":"MethylCentroid","project":${var.projectPath},'
            '"phase":${var.phase},"runId":${var.runId},"taskConfig":${var.taskConfig}}'
        )
        resolved = resolve_template(template, scope)
        payload = json.loads(resolved)
        self.assertEqual(payload["project"], "/work/run_0001")
        self.assertEqual(payload["runId"], "feature_run_0001")
        self.assertEqual(payload["taskConfig"]["iteration"], 1)
        self.assertEqual(payload["taskConfig"]["trainFraction"], 0.8)

    def test_validation_mc_fixture_shape(self) -> None:
        from pathlib import Path

        fixture = Path(__file__).resolve().parents[1] / "sql/instance_context_examples/validation_mc.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertIn("iterations", data)
        first = data["iterations"][0]
        scope = flatten_foreach_element(first, index=0)
        self.assertIn("taskConfig", scope)
        self.assertTrue(scope["taskConfig"].startswith("{"))

    def test_gene_select_template_resolves_run_dir(self) -> None:
        from methyl_validation.planner_models import ValidationPlannedIteration
        from methyl_worker.task_validation import normalize_task_input
        from workflow_engine.domain.compiler import compile_domain_program_file
        from workflow_engine.local.resolver import resolve_input_template
        from workflow_engine.local.scope import flatten_foreach_element

        iteration = ValidationPlannedIteration.model_validate(
            {
                "$type": "StratifiedCohortDraw",
                "runId": "feature_run_0001",
                "phase": "feature",
                "projectPath": "/work/demo/monte_carlo_runs/run_0001/project.json",
                "runDir": "/work/demo/monte_carlo_runs/run_0001",
                "taskConfig": {
                    "runId": "feature_run_0001",
                    "phase": "feature",
                    "iteration": 1,
                    "layout": "binary",
                    "trainFraction": 0.8,
                    "projectJson": "/work/demo/monte_carlo_runs/run_0001/project.json",
                    "runDir": "/work/demo/monte_carlo_runs/run_0001",
                    "monteCarloRunsRoot": "/work/demo/monte_carlo_runs",
                },
            }
        ).model_dump(mode="json", by_alias=True)
        scope = flatten_foreach_element(
            iteration, item_var="iteration", index_var="iterIndex", index=0
        )
        flat = dict(scope)
        program_path = (
            Path(__file__).resolve().parents[1]
            / "domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json"
        )
        compiled = compile_domain_program_file(program_path, enrich_context=False)
        gene_select = next(n for n in compiled.workflow.nodes if n.node_key == "gene_select")
        resolved = resolve_input_template(gene_select.input_template, flat)
        payload = normalize_task_input("pipeline.gene_select", "pipeline.gene_select", resolved)
        self.assertEqual(payload["runDir"], "/work/demo/monte_carlo_runs/run_0001")
        self.assertEqual(
            payload["projectPath"], "/work/demo/monte_carlo_runs/run_0001/project.json"
        )


if __name__ == "__main__":
    unittest.main()
