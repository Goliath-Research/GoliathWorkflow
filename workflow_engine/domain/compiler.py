"""
Lower DomainProgram IR to WorkflowDefinitionSpec + context_json.

The workflow engine remains object-agnostic; this compiler emits standard
ACTION / SEQUENCE / FOREACH / IF nodes and output bindings.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from methyl_domain.program import ActionStep, DomainProgram, ForeachStep, IfStep

_CONTRACT = Path(__file__).resolve().parents[1] / "contract"
if str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))

from workflow_definition_spec import (  # noqa: E402
    WorkflowDefinitionSpec,
    WorkflowEdgeSpec,
    WorkflowInputBindingSpec,
    WorkflowNodeSpec,
    WorkflowOutputBindingSpec,
    WorkflowScopeDefaultSpec,
)

_WORKERS = Path(__file__).resolve().parents[2] / "workers"
if str(_WORKERS) not in sys.path:
    sys.path.insert(0, str(_WORKERS))

from methyl_worker.action_catalog import find_catalog_entry  # noqa: E402


@dataclass
class CompileResult:
    workflow: WorkflowDefinitionSpec
    context_json: Dict[str, Any]


@dataclass
class _CompileCtx:
    nodes: List[WorkflowNodeSpec] = field(default_factory=list)
    edges: List[WorkflowEdgeSpec] = field(default_factory=list)
    output_bindings: List[WorkflowOutputBindingSpec] = field(default_factory=list)
    scope_defaults: List[WorkflowScopeDefaultSpec] = field(default_factory=list)
    input_bindings: List[WorkflowInputBindingSpec] = field(default_factory=list)
    _counter: int = 0

    def fresh_key(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"


def _parse_step(raw: Any) -> Any:
    if isinstance(raw, (ActionStep, IfStep, ForeachStep)):
        return raw
    if not isinstance(raw, dict):
        raise ValueError(f"unsupported program step: {raw!r}")
    if "action" in raw:
        return ActionStep.model_validate(raw)
    if "if" in raw:
        return IfStep.model_validate(raw)
    if "foreach" in raw:
        return ForeachStep.model_validate(raw)
    raise ValueError(f"unsupported program step keys: {list(raw)}")


def _condition_var_from_expr(expr: str) -> str:
    expr = expr.strip()
    m = re.match(r"^\$\{(.+)\}$", expr)
    inner = m.group(1) if m else expr
    if "==" in inner:
        return inner.split("==", 1)[0].strip()
    return inner.strip()


def _action_template(entry, step: ActionStep) -> Dict[str, Any]:
    tool = entry.tool or entry.action_name
    template: Dict[str, Any] = {"tool": tool}
    if entry.step_config_key:
        template["project"] = "${var.projectPath}"
    for ctx_var in entry.context_vars:
        template[ctx_var] = f"${{var.{ctx_var}}}"
    if step.in_:
        for _k, v in step.in_.items():
            if v.startswith("${") and v.endswith("}"):
                template[_k] = v
    return template


def _link(parent: str, child: str, order: int, branch: str, ctx: _CompileCtx) -> None:
    ctx.edges.append(
        WorkflowEdgeSpec(
            parent_node_key=parent,
            child_node_key=child,
            child_order=order,
            branch_kind=branch,  # type: ignore[arg-type]
        )
    )


def _compile_action(ctx: _CompileCtx, step: ActionStep, parent_key: str, order: int) -> str:
    entry = find_catalog_entry(step.action)
    if entry is None:
        raise ValueError(f"unknown action in program: {step.action!r}")
    node_key = step.node_key or ctx.fresh_key(step.action.replace(".", "_"))
    ctx.nodes.append(
        WorkflowNodeSpec(
            node_key=node_key,
            node_type="ACTION",
            action_name=entry.action_name,
            input_template=_action_template(entry, step),
        )
    )
    _link(parent_key, node_key, order, "SEQUENCE", ctx)
    if entry.action_name == "sample.methyl_qc":
        ctx.output_bindings.append(
            WorkflowOutputBindingSpec(
                node_key=node_key,
                var_name="qcPass",
                source_kind="output_path",
                source_json_path="$.guardrails.overall_pass",
            )
        )
    return node_key


def _compile_if(ctx: _CompileCtx, step: IfStep, parent_key: str, order: int) -> str:
    if_key = ctx.fresh_key("if")
    cond_var = _condition_var_from_expr(step.if_)
    ctx.nodes.append(
        WorkflowNodeSpec(node_key=if_key, node_type="IF", condition_var=cond_var)
    )
    _link(parent_key, if_key, order, "SEQUENCE", ctx)
    then_key = _compile_steps(ctx, step.then, if_key, branch="THEN")
    _link(if_key, then_key, 0, "THEN", ctx)
    if step.else_:
        else_key = _compile_steps(ctx, step.else_, if_key, branch="ELSE")
        _link(if_key, else_key, 1, "ELSE", ctx)
    return if_key


def _compile_foreach(ctx: _CompileCtx, step: ForeachStep, parent_key: str, order: int) -> str:
    fe_key = ctx.fresh_key("foreach")
    spec = step.foreach
    ctx.nodes.append(
        WorkflowNodeSpec(
            node_key=fe_key,
            node_type="FOREACH",
            foreach_collection_var=spec.collection,
            foreach_item_var=spec.item,
            foreach_index_var=spec.index or f"{spec.item}Index",
            foreach_parallel=spec.parallel,
        )
    )
    _link(parent_key, fe_key, order, "SEQUENCE", ctx)
    body_key = _compile_steps(ctx, step.steps, fe_key, branch="BODY")
    _link(fe_key, body_key, 0, "BODY", ctx)
    return fe_key


def _compile_steps(
    ctx: _CompileCtx,
    steps: List[Any],
    parent_key: str,
    *,
    branch: str = "SEQUENCE",
) -> str:
    seq_key = ctx.fresh_key("seq")
    ctx.nodes.append(WorkflowNodeSpec(node_key=seq_key, node_type="SEQUENCE"))
    if branch != "SEQUENCE":
        _link(parent_key, seq_key, 0, branch, ctx)
    for order, raw in enumerate(steps):
        step = _parse_step(raw)
        if isinstance(step, ActionStep):
            _compile_action(ctx, step, seq_key, order)
        elif isinstance(step, IfStep):
            _compile_if(ctx, step, seq_key, order)
        elif isinstance(step, ForeachStep):
            _compile_foreach(ctx, step, seq_key, order)
    return seq_key


def compile_domain_program(program: DomainProgram) -> CompileResult:
    ctx = _CompileCtx()
    root_key = "root"
    ctx.nodes.append(WorkflowNodeSpec(node_key=root_key, node_type="SEQUENCE"))

    for order, phase in enumerate(program.phases):
        if phase.foreach:
            fe_key = ctx.fresh_key(f"phase_{phase.name}")
            spec = phase.foreach
            ctx.nodes.append(
                WorkflowNodeSpec(
                    node_key=fe_key,
                    node_type="FOREACH",
                    foreach_collection_var=spec.collection,
                    foreach_item_var=spec.item,
                    foreach_index_var=spec.index or f"{spec.item}Index",
                    foreach_parallel=spec.parallel,
                )
            )
            _link(root_key, fe_key, order, "SEQUENCE", ctx)
            body_key = _compile_steps(ctx, phase.steps, fe_key, branch="BODY")
            _link(fe_key, body_key, 0, "BODY", ctx)
        else:
            phase_seq = _compile_steps(ctx, phase.steps, root_key)
            _link(root_key, phase_seq, order, "SEQUENCE", ctx)

    context_json: Dict[str, Any] = {"projectPath": program.projectPath, **program.variables}

    workflow = WorkflowDefinitionSpec(
        name=program.name,
        description=program.description,
        root_node_key=root_key,
        nodes=ctx.nodes,
        edges=ctx.edges,
        output_bindings=ctx.output_bindings,
        scope_defaults=ctx.scope_defaults,
        input_bindings=ctx.input_bindings,
    )
    return CompileResult(workflow=workflow, context_json=context_json)


def compile_domain_program_file(path: Path) -> CompileResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    return compile_domain_program(DomainProgram.model_validate(data))
