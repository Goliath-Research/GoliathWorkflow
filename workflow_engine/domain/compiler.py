"""
Lower DomainProgram IR to WorkflowDefinitionSpec + context_json.

Supports program v1 (phases/steps) and v2 (statement body with for/parallel/do).
Emits collection_bindings for project.* references resolved by the engine at instance start.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from methyl_domain.program import (
    ActionStep,
    CollectionInSpec,
    DomainProgram,
    ForeachSpec,
    ForeachStep,
    IfStep,
    ParallelStep,
)

_CONTRACT = Path(__file__).resolve().parents[1] / "contract"
if str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))

from workflow_definition_spec import (  # noqa: E402
    CollectionBindingSpec,
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

from workflow_context import enrich_instance_context  # noqa: E402


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
    collection_bindings: List[CollectionBindingSpec] = field(default_factory=list)
    _counter: int = 0

    def fresh_key(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"


def _parse_step(raw: Any) -> Union[ActionStep, IfStep, ForeachStep, ParallelStep]:
    if isinstance(raw, (ActionStep, IfStep, ForeachStep, ParallelStep)):
        return raw
    if not isinstance(raw, dict):
        raise ValueError(f"unsupported program step: {raw!r}")
    if "parallel" in raw and isinstance(raw.get("parallel"), list):
        return ParallelStep.model_validate(raw)
    if "for" in raw or "foreach" in raw:
        return ForeachStep.model_validate(raw)
    if "if" in raw:
        return IfStep.model_validate(raw)
    if "do" in raw or "action" in raw:
        return ActionStep.model_validate(raw)
    raise ValueError(f"unsupported program step keys: {list(raw)}")


def _condition_var_from_expr(expr: str) -> str:
    expr = expr.strip()
    m = re.match(r"^\$\{(.+)\}$", expr)
    inner = m.group(1) if m else expr
    if "==" in inner:
        return inner.split("==", 1)[0].strip()
    return inner.strip()


def _ref_to_var(ref: str) -> str:
    """Map a program ref to a flattened scope variable name."""
    if ref.startswith("${") and ref.endswith("}"):
        return ref[2:-1].replace("var.", "")
    parts = ref.split(".")
    return parts[-1]


def _placeholder_for_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "ref" in value:
            return f"${{var.{_ref_to_var(str(value['ref']))}}}"
        return {k: _placeholder_for_value(v) for k, v in value.items()}
    if isinstance(value, str):
        if value.startswith("${"):
            return value
        return value
    return value


def _collect_project_binding(ref: str, bindings: Dict[str, CollectionBindingSpec]) -> None:
    if not ref.startswith("project."):
        return
    field_name = ref.split(".", 1)[1]
    if field_name == "project":
        return
    bindings.setdefault(
        "project",
        CollectionBindingSpec(
            scope_var="project",
            kind="jsonFile",
            path_var="projectPath",
            bind_order=0,
        ),
    )
    bindings[field_name] = CollectionBindingSpec(
        scope_var=field_name,
        kind="jsonPath",
        base_var="project",
        json_path=f"$.{field_name}",
        bind_order=len(bindings),
    )


def _collect_bindings_from_spec(spec: ForeachSpec, bindings: Dict[str, CollectionBindingSpec]) -> None:
    if isinstance(spec.in_, CollectionInSpec):
        if spec.in_.ref:
            _collect_project_binding(spec.in_.ref, bindings)
        return
    if isinstance(spec.in_, str) and spec.in_.startswith("project."):
        _collect_project_binding(spec.in_, bindings)


def _collect_bindings_from_steps(steps: List[Any], bindings: Dict[str, CollectionBindingSpec]) -> None:
    for raw in steps:
        step = _parse_step(raw)
        if isinstance(step, ForeachStep):
            _collect_bindings_from_spec(step.spec(), bindings)
            _collect_bindings_from_steps(step.body(), bindings)
        elif isinstance(step, IfStep):
            _collect_bindings_from_steps(step.then, bindings)
            _collect_bindings_from_steps(step.else_, bindings)
        elif isinstance(step, ParallelStep):
            _collect_bindings_from_steps(step.parallel, bindings)


def _build_collection_bindings(program: DomainProgram) -> List[CollectionBindingSpec]:
    bindings: Dict[str, CollectionBindingSpec] = {}
    bindings["project"] = CollectionBindingSpec(
        scope_var="project",
        kind="jsonFile",
        path_var="projectPath",
        bind_order=0,
    )
    if program.body:
        _collect_bindings_from_steps(program.body, bindings)
    for phase in program.phases:
        if phase.foreach:
            _collect_bindings_from_spec(phase.foreach, bindings)
        _collect_bindings_from_steps(phase.steps, bindings)
    ordered = sorted(bindings.values(), key=lambda b: (b.bind_order, b.scope_var))
    for i, b in enumerate(ordered):
        b.bind_order = i
    return ordered


def _group_ref_side(ref: Any) -> Optional[str]:
    """Return 'control' or 'disease' when step.with group references comparison sides."""
    if isinstance(ref, dict) and "ref" in ref:
        ref_s = str(ref["ref"])
    elif isinstance(ref, str):
        ref_s = ref
    else:
        return None
    if "control_group" in ref_s:
        return "control"
    if "disease_group" in ref_s:
        return "disease"
    return None


def _action_template(entry, step: ActionStep) -> Dict[str, Any]:
    tool = entry.tool or entry.action_name
    template: Dict[str, Any] = {"tool": tool}
    template["projectPath"] = "${var.projectPath}"
    if entry.step_config_key:
        template["project"] = "${var.projectPath}"
    for ctx_var in entry.context_vars:
        template[ctx_var] = f"${{var.{ctx_var}}}"

    params = step.with_ or step.in_ or {}
    for key, val in params.items():
        template[key] = _placeholder_for_value(val)

    action = entry.action_name
    if action == "pipeline.centroid":
        side = _group_ref_side(params.get("group"))
        if side == "control":
            template["outputDir"] = "${var.centroid1Dir}"
        elif side == "disease":
            template["outputDir"] = "${var.centroid2Dir}"
    elif action == "pipeline.detector":
        template["centroid1Dir"] = "${var.centroid1Dir}"
        template["centroid2Dir"] = "${var.centroid2Dir}"
        template["outputDir"] = "${var.detectOutDir}"
        if "comparison" not in template and "label" not in template:
            template["comparison"] = "${var.label}"

    return template


def _emit_root_scope_defaults(ctx: _CompileCtx, root_key: str) -> None:
    ctx.scope_defaults.extend(
        [
            WorkflowScopeDefaultSpec(
                node_key=root_key,
                var_name="projectPath",
                default_expr="${var.projectPath}",
            ),
            WorkflowScopeDefaultSpec(
                node_key=root_key,
                var_name="centroid1Dir",
                default_expr="${var.centroid1Dir}",
            ),
        ]
    )


def _link(parent: str, child: str, order: int, branch: str, ctx: _CompileCtx) -> None:
    ctx.edges.append(
        WorkflowEdgeSpec(
            parent_node_key=parent,
            child_node_key=child,
            child_order=order,
            branch_kind=branch,  # type: ignore[arg-type]
        )
    )


def _compile_action(
    ctx: _CompileCtx, step: ActionStep, parent_key: str, order: int, *, branch: str = "SEQUENCE"
) -> str:
    action_name = step.action_name()
    entry = find_catalog_entry(action_name)
    if entry is None:
        raise ValueError(f"unknown action in program: {action_name!r}")
    node_key = step.node_key or ctx.fresh_key(action_name.replace(".", "_"))
    ctx.nodes.append(
        WorkflowNodeSpec(
            node_key=node_key,
            node_type="ACTION",
            action_name=entry.action_name,
            input_template=_action_template(entry, step),
        )
    )
    _link(parent_key, node_key, order, branch, ctx)
    if entry.domain_effects and entry.domain_effects.scope_bindings:
        for var_name, json_path in entry.domain_effects.scope_bindings:
            ctx.output_bindings.append(
                WorkflowOutputBindingSpec(
                    node_key=node_key,
                    var_name=var_name,
                    source_kind="output_path",
                    source_json_path=json_path,
                )
            )
    if entry.domain_effects and entry.domain_effects.output_bindings:
        for binding in entry.domain_effects.output_bindings:
            ctx.output_bindings.append(
                WorkflowOutputBindingSpec(
                    node_key=node_key,
                    var_name=binding.scope_field,
                    source_kind="output_path",
                    source_json_path=binding.output_json_path,
                )
            )
    return node_key


def _compile_if(
    ctx: _CompileCtx, step: IfStep, parent_key: str, order: int, *, branch: str = "SEQUENCE"
) -> str:
    if_key = ctx.fresh_key("if")
    cond_var = _condition_var_from_expr(step.if_)
    ctx.nodes.append(
        WorkflowNodeSpec(node_key=if_key, node_type="IF", condition_var=cond_var)
    )
    _link(parent_key, if_key, order, branch, ctx)
    _compile_steps(ctx, step.then, if_key, branch="THEN")
    if step.else_:
        _compile_steps(ctx, step.else_, if_key, branch="ELSE")
    return if_key


def _compile_foreach(
    ctx: _CompileCtx, step: ForeachStep, parent_key: str, order: int, *, branch: str = "SEQUENCE"
) -> str:
    fe_key = ctx.fresh_key("foreach")
    spec = step.spec()
    item = spec.resolved_item()
    ctx.nodes.append(
        WorkflowNodeSpec(
            node_key=fe_key,
            node_type="FOREACH",
            foreach_collection_var=spec.resolved_collection_var(),
            foreach_item_var=item,
            foreach_index_var=spec.index or f"{item}Index",
            foreach_parallel=spec.parallel,
        )
    )
    _link(parent_key, fe_key, order, branch, ctx)
    _compile_steps(ctx, step.body(), fe_key, branch="BODY")
    return fe_key


def _compile_parallel(
    ctx: _CompileCtx, step: ParallelStep, parent_key: str, order: int, *, branch: str = "SEQUENCE"
) -> str:
    par_key = ctx.fresh_key("parallel")
    ctx.nodes.append(WorkflowNodeSpec(node_key=par_key, node_type="PARALLEL"))
    _link(parent_key, par_key, order, branch, ctx)
    for idx, raw in enumerate(step.parallel):
        child = _parse_step(raw)
        if isinstance(child, ActionStep):
            _compile_action(ctx, child, par_key, idx, branch="PARALLEL")
        elif isinstance(child, IfStep):
            _compile_if(ctx, child, par_key, idx, branch="PARALLEL")
        elif isinstance(child, ForeachStep):
            _compile_foreach(ctx, child, par_key, idx, branch="PARALLEL")
        elif isinstance(child, ParallelStep):
            _compile_parallel(ctx, child, par_key, idx, branch="PARALLEL")
    return par_key


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
        elif isinstance(step, ParallelStep):
            _compile_parallel(ctx, step, seq_key, order)
    return seq_key


def compile_domain_program(program: DomainProgram, *, enrich_context: bool = False) -> CompileResult:
    ctx = _CompileCtx()
    root_key = "root"
    ctx.nodes.append(WorkflowNodeSpec(node_key=root_key, node_type="SEQUENCE"))

    if program.body:
        body_seq = _compile_steps(ctx, program.body, root_key)
        _link(root_key, body_seq, 0, "SEQUENCE", ctx)
    else:
        for order, phase in enumerate(program.phases):
            if phase.foreach:
                fe_key = ctx.fresh_key(f"phase_{phase.name}")
                spec = phase.foreach
                ctx.nodes.append(
                    WorkflowNodeSpec(
                        node_key=fe_key,
                        node_type="FOREACH",
                        foreach_collection_var=spec.resolved_collection_var(),
                        foreach_item_var=spec.resolved_item(),
                        foreach_index_var=spec.index or f"{spec.resolved_item()}Index",
                        foreach_parallel=spec.parallel,
                    )
                )
                _link(root_key, fe_key, order, "SEQUENCE", ctx)
                _compile_steps(ctx, phase.steps, fe_key, branch="BODY")
            else:
                phase_seq = _compile_steps(ctx, phase.steps, root_key)
                _link(root_key, phase_seq, order, "SEQUENCE", ctx)

    collection_bindings = _build_collection_bindings(program)
    context_json: Dict[str, Any] = {"projectPath": program.projectPath, **program.variables}
    if enrich_context:
        try:
            context_json = enrich_instance_context(context_json)
        except (FileNotFoundError, ValueError):
            pass

    _emit_root_scope_defaults(ctx, root_key)

    workflow = WorkflowDefinitionSpec(
        name=program.name,
        description=program.description,
        root_node_key=root_key,
        nodes=ctx.nodes,
        edges=ctx.edges,
        output_bindings=ctx.output_bindings,
        scope_defaults=ctx.scope_defaults,
        input_bindings=ctx.input_bindings,
        collection_bindings=collection_bindings,
    )
    return CompileResult(workflow=workflow, context_json=context_json)


def compile_domain_program_file(path: Path, *, enrich_context: bool = False) -> CompileResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    return compile_domain_program(DomainProgram.model_validate(data), enrich_context=enrich_context)
