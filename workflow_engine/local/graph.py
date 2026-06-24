"""Workflow graph adjacency from WorkflowDefinitionSpec."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from workflow_definition_spec import BranchKind, WorkflowDefinitionSpec, WorkflowNodeSpec


@dataclass
class WorkflowGraph:
    root_key: str
    nodes: Dict[str, WorkflowNodeSpec]
    children: Dict[str, Dict[Optional[BranchKind], List[Tuple[int, str]]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )

    def child_keys(
        self,
        parent_key: str,
        branch: Optional[BranchKind] = None,
    ) -> List[str]:
        by_branch = self.children.get(parent_key, {})
        if branch is not None:
            ordered = sorted(by_branch.get(branch, []), key=lambda t: t[0])
            return [k for _, k in ordered]
        # Default SEQUENCE children when branch unspecified
        ordered = sorted(by_branch.get("SEQUENCE", []), key=lambda t: t[0])
        if ordered:
            return [k for _, k in ordered]
        # IF/FOREACH: single BODY
        body = sorted(by_branch.get("BODY", []), key=lambda t: t[0])
        if body:
            return [k for _, k in body]
        return []

    def then_child(self, if_key: str) -> Optional[str]:
        keys = self.child_keys(if_key, "THEN")
        return keys[0] if keys else None

    def else_child(self, if_key: str) -> Optional[str]:
        keys = self.child_keys(if_key, "ELSE")
        return keys[0] if keys else None

    def body_child(self, parent_key: str) -> Optional[str]:
        keys = self.child_keys(parent_key, "BODY")
        return keys[0] if keys else None

    def parallel_children(self, parent_key: str) -> List[str]:
        return self.child_keys(parent_key, "PARALLEL")

    def switch_case_child(self, switch_key: str, case_value: int) -> Optional[str]:
        by_branch = self.children.get(switch_key, {})
        for branch, items in by_branch.items():
            if branch == "CASE":
                # CASE edges store switch_case_value on edge - we need edge metadata
                pass
        return None


def build_graph(spec: WorkflowDefinitionSpec) -> WorkflowGraph:
    nodes = {n.node_key: n for n in spec.nodes}
    graph = WorkflowGraph(root_key=spec.root_node_key, nodes=nodes)
    for edge in spec.edges:
        graph.children[edge.parent_node_key][edge.branch_kind].append(
            (edge.child_order, edge.child_node_key)
        )
    return graph


@dataclass
class SwitchEdgeIndex:
    """Maps SWITCH parent -> case value -> child key."""

    cases: Dict[str, Dict[int, str]] = field(default_factory=lambda: defaultdict(dict))
    defaults: Dict[str, str] = field(default_factory=dict)


def build_switch_index(spec: WorkflowDefinitionSpec) -> SwitchEdgeIndex:
    idx = SwitchEdgeIndex()
    for edge in spec.edges:
        if edge.branch_kind == "CASE" and edge.switch_case_value is not None:
            idx.cases[edge.parent_node_key][edge.switch_case_value] = edge.child_node_key
        elif edge.branch_kind == "DEFAULT" or edge.is_default:
            idx.defaults[edge.parent_node_key] = edge.child_node_key
    return idx
