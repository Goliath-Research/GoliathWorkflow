"""Workflow node scheduler — executes graph with full control-flow semantics."""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from workflow_definition_spec import WorkflowDefinitionSpec, WorkflowNodeSpec

from .bindings import apply_catalog_scope_bindings, apply_output_bindings
from .conditions import scope_var_int, scope_var_truthy
from .graph import WorkflowGraph, build_graph, build_switch_index
from .resolver import resolve_input_template
from .scope import ScopeFrame, apply_scope_defaults, flatten_foreach_element

logger = logging.getLogger(__name__)

_WORKERS = Path(__file__).resolve().parents[2] / "workers"
if str(_WORKERS) not in sys.path:
    sys.path.insert(0, str(_WORKERS))

ActionHandler = Callable[[str, str, Dict[str, Any]], BaseModel]


class NodeExecutionError(RuntimeError):
    """Wraps scheduler failures with workflow node context."""

    def __init__(self, node_key: str, node_type: str, action_name: str | None, cause: BaseException):
        self.node_key = node_key
        self.node_type = node_type
        self.action_name = action_name
        self.cause = cause
        label = action_name or node_type
        super().__init__(f"node {node_key!r} ({label}): {cause}")


@dataclass
class SchedulerConfig:
    parallel_workers: int = 4
    dry_run: bool = False
    force_rerun: bool = False


@dataclass
class ExecutionTrace:
    executed_actions: List[str] = field(default_factory=list)
    skipped_actions: List[str] = field(default_factory=list)
    skipped_branches: List[str] = field(default_factory=list)


class WorkflowScheduler:
    def __init__(
        self,
        spec: WorkflowDefinitionSpec,
        scope: ScopeFrame,
        *,
        handler: ActionHandler,
        config: Optional[SchedulerConfig] = None,
    ) -> None:
        self.spec = spec
        self.scope = scope
        self.handler = handler
        self.config = config or SchedulerConfig()
        self.graph = build_graph(spec)
        self.switch_index = build_switch_index(spec)
        self.trace = ExecutionTrace()

    def run(self) -> ExecutionTrace:
        apply_scope_defaults(self.spec, self.scope, self.graph.root_key)
        self._execute_node(self.graph.root_key, self.scope)
        return self.trace

    def _execute_node(self, node_key: str, scope: ScopeFrame) -> None:
        node = self.graph.nodes[node_key]
        apply_scope_defaults(self.spec, scope, node_key)

        try:
            self._execute_node_inner(node_key, node, scope)
        except NodeExecutionError:
            raise
        except Exception as exc:
            raise NodeExecutionError(
                node_key,
                node.node_type,
                node.action_name,
                exc,
            ) from exc

    def _execute_node_inner(self, node_key: str, node: WorkflowNodeSpec, scope: ScopeFrame) -> None:
        if node.node_type == "SEQUENCE":
            for child in self.graph.child_keys(node_key, "SEQUENCE"):
                self._execute_node(child, scope)
            return

        if node.node_type == "PARALLEL":
            children = self.graph.parallel_children(node_key)
            if not children:
                return
            if self.config.parallel_workers <= 1 or len(children) == 1:
                for child in children:
                    self._execute_node(child, scope.child())
                return
            with ThreadPoolExecutor(max_workers=self.config.parallel_workers) as pool:
                futures = {
                    pool.submit(self._execute_node, child, scope.child()): child for child in children
                }
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except NodeExecutionError as exc:
                        child_key = futures[fut]
                        raise NodeExecutionError(
                            node_key,
                            "PARALLEL",
                            None,
                            RuntimeError(f"parallel child {child_key!r} failed: {exc.cause}"),
                        ) from exc
            return

        if node.node_type == "FOREACH":
            self._execute_foreach(node, scope)
            return

        if node.node_type == "IF":
            self._execute_if(node, scope)
            return

        if node.node_type == "SWITCH":
            self._execute_switch(node, scope)
            return

        if node.node_type == "WHILE":
            self._execute_while(node, scope)
            return

        if node.node_type == "REPEAT":
            self._execute_repeat(node, scope)
            return

        if node.node_type == "ACTION":
            self._execute_action(node, scope)
            return

        raise RuntimeError(f"unsupported node_type {node.node_type!r} at {node_key}")

    def _execute_foreach(self, node: WorkflowNodeSpec, scope: ScopeFrame) -> None:
        coll_var = node.foreach_collection_var or ""
        collection = scope.get(coll_var)
        if collection is None:
            collection = []
        if not isinstance(collection, list):
            raise RuntimeError(f"FOREACH {node.node_key}: {coll_var!r} is not a list")
        body = self.graph.body_child(node.node_key)
        if not body:
            return
        item_var = node.foreach_item_var or "item"
        index_var = node.foreach_index_var or "index"
        parallel = bool(node.foreach_parallel)

        from foreach_caas import (
            canonical_item_payload,
            child_action_revisions,
            collect_body_action_names,
            commit_iteration_bundle_local,
            foreach_caas_enabled,
            probe_iteration_bundle,
        )
        from methyl_domain.foreach_bundle import resolve_study_root_from_scope

        flat = scope.as_flat_dict()
        caas_on = foreach_caas_enabled(flat) and not self.config.force_rerun
        project_root = resolve_study_root_from_scope(flat) if caas_on else None
        revisions = child_action_revisions(collect_body_action_names(self.graph, body))

        def run_one(idx: int, element: Any) -> None:
            item_payload = canonical_item_payload(element)
            if caas_on:
                hit = probe_iteration_bundle(
                    project_root,
                    foreach_node_key=node.node_key,
                    collection_var=coll_var,
                    iteration_index=idx,
                    item_payload=item_payload,
                    child_revisions=revisions,
                    enabled=True,
                )
                if hit is not None:
                    self.trace.skipped_branches.append(
                        f"{node.node_key}:BODY[{idx}]:foreach_caas"
                    )
                    return
            child_scope = scope.child(
                flatten_foreach_element(
                    element, item_var=item_var, index_var=index_var, index=idx
                )
            )
            self._execute_node(body, child_scope)
            if caas_on:
                # Re-resolve root after BODY (prepare_freeze may rebind projectPath).
                child_flat = child_scope.as_flat_dict()
                root = resolve_study_root_from_scope(child_flat) or project_root
                commit_iteration_bundle_local(
                    root,
                    foreach_node_key=node.node_key,
                    collection_var=coll_var,
                    iteration_index=idx,
                    item_payload=item_payload,
                    child_revisions=revisions,
                    enabled=True,
                )

        if parallel and self.config.parallel_workers > 1 and len(collection) > 1:
            with ThreadPoolExecutor(max_workers=self.config.parallel_workers) as pool:
                futures = [pool.submit(run_one, i, el) for i, el in enumerate(collection)]
                for fut in as_completed(futures):
                    fut.result()
        else:
            for idx, element in enumerate(collection):
                run_one(idx, element)

    def _execute_if(self, node: WorkflowNodeSpec, scope: ScopeFrame) -> None:
        cond_var = node.condition_var or ""
        if scope_var_truthy(scope, cond_var):
            then_key = self.graph.then_child(node.node_key)
            if then_key:
                self._execute_node(then_key, scope)
        else:
            self.trace.skipped_branches.append(f"{node.node_key}:THEN")
            else_key = self.graph.else_child(node.node_key)
            if else_key:
                self._execute_node(else_key, scope)
            else:
                self.trace.skipped_branches.append(f"{node.node_key}:ELSE")

    def _execute_switch(self, node: WorkflowNodeSpec, scope: ScopeFrame) -> None:
        switch_var = node.switch_var or ""
        val = scope_var_int(scope, switch_var)
        child = self.switch_index.cases.get(node.node_key, {}).get(val)
        if child is None:
            child = self.switch_index.defaults.get(node.node_key)
        if child:
            self._execute_node(child, scope)

    def _execute_while(self, node: WorkflowNodeSpec, scope: ScopeFrame) -> None:
        cond_var = node.condition_var or ""
        body = self.graph.body_child(node.node_key)
        if not body:
            return
        guard = 0
        while scope_var_truthy(scope, cond_var):
            guard += 1
            if guard > 10_000:
                raise RuntimeError(f"WHILE {node.node_key} exceeded iteration guard")
            self._execute_node(body, scope)

    def _execute_repeat(self, node: WorkflowNodeSpec, scope: ScopeFrame) -> None:
        count = int(node.repeat_count or 0)
        body = self.graph.body_child(node.node_key)
        if not body:
            return
        for _ in range(count):
            self._execute_node(body, scope)

    def _execute_action(self, node: WorkflowNodeSpec, scope: ScopeFrame) -> None:
        action_name = node.action_name or ""
        template = node.input_template or {}
        flat = scope.as_flat_dict()
        input_json = resolve_input_template(template, flat)
        input_json["workflowNodeKey"] = node.node_key
        if self.config.force_rerun or flat.get("forceRerun") is True:
            input_json["forceRerun"] = True

        from methyl_worker.action_catalog import find_catalog_entry

        entry = find_catalog_entry(action_name)
        capability = entry.capability if entry else action_name

        from workflow_context import materialize_action_input

        input_json = materialize_action_input(input_json, action_name, flat)

        if self.config.dry_run:
            logger.info("dry-run ACTION %s: %s", action_name, input_json)
            self.trace.executed_actions.append(node.node_key)
            return

        output = self.handler(capability, action_name, input_json)
        apply_output_bindings(self.spec, node.node_key, output, scope)
        if action_name:
            apply_catalog_scope_bindings(action_name, output, scope)
        # prepare_freeze rebinds projectPath to production/; refresh comparison
        # artifact dirs so FOREACH flatten does not keep study-root centroid2Dir.
        if action_name == "validation.prepare_freeze_project":
            prod_path = scope.get("projectPath")
            if prod_path:
                try:
                    from workflow_context import enrich_comparisons_from_project

                    scope["comparisons"] = enrich_comparisons_from_project(Path(str(prod_path)))
                    first = (scope.get("comparisons") or [None])[0]
                    if isinstance(first, dict):
                        if first.get("centroid1Dir"):
                            scope["centroid1Dir"] = first["centroid1Dir"]
                        if first.get("centroid2Dir"):
                            scope["centroid2Dir"] = first["centroid2Dir"]
                        if first.get("detectOutDir"):
                            scope["detectOutDir"] = first["detectOutDir"]
                except Exception:
                    logger.debug(
                        "could not refresh comparisons after prepare_freeze",
                        exc_info=True,
                    )
        status = getattr(output, "status", None)
        if status == "skipped":
            self.trace.skipped_actions.append(node.node_key)
        else:
            self.trace.executed_actions.append(node.node_key)
