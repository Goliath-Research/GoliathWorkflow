"""Workflow node scheduler — executes graph with full control-flow semantics."""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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


ActionHandler = Callable[[str, str, Dict[str, Any]], Dict[str, Any]]


@dataclass
class SchedulerConfig:
    parallel_workers: int = 4
    dry_run: bool = False


@dataclass
class ExecutionTrace:
    executed_actions: List[str] = field(default_factory=list)
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
                futures = [
                    pool.submit(self._execute_node, child, scope.child()) for child in children
                ]
                for fut in as_completed(futures):
                    fut.result()
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

        def run_one(idx: int, element: Any) -> None:
            child_scope = scope.child(
                flatten_foreach_element(
                    element, item_var=item_var, index_var=index_var, index=idx
                )
            )
            self._execute_node(body, child_scope)

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

        from methyl_worker.action_catalog import find_catalog_entry

        entry = find_catalog_entry(action_name)
        capability = entry.capability if entry else action_name

        if self.config.dry_run:
            logger.info("dry-run ACTION %s: %s", action_name, input_json)
            self.trace.executed_actions.append(node.node_key)
            return

        output = self.handler(capability, action_name, input_json)
        apply_output_bindings(self.spec, node.node_key, output, scope)
        if action_name:
            apply_catalog_scope_bindings(action_name, output, scope)
        self.trace.executed_actions.append(node.node_key)
