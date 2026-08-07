"""Structural + catalog verification for compiled DomainPrograms / workflow IR."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

_DOMAIN_DIR = Path(__file__).resolve().parent
if str(_DOMAIN_DIR) not in sys.path:
    sys.path.insert(0, str(_DOMAIN_DIR))

from compiler import CompileResult, compile_domain_program_file  # noqa: E402


@dataclass
class Finding:
    severity: str  # error | warning | info
    code: str
    message: str


@dataclass
class VerifyReport:
    program_name: str
    findings: List[Finding] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    action_names: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "program_name": self.program_name,
            "ok": self.ok,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "action_names": sorted(set(self.action_names)),
            "findings": [
                {"severity": f.severity, "code": f.code, "message": f.message}
                for f in self.findings
            ],
        }


def _node_map(nodes: Sequence[Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for n in nodes:
        key = getattr(n, "node_key", None) or (n.get("node_key") if isinstance(n, Mapping) else None)
        if key:
            out[str(key)] = n
    return out


def _attr(node: Any, name: str, default: Any = None) -> Any:
    if hasattr(node, name):
        return getattr(node, name)
    if isinstance(node, Mapping):
        return node.get(name, default)
    return default


def verify_compiled_workflow(
    compiled: CompileResult | Mapping[str, Any],
    *,
    catalog_action_names: Optional[Set[str]] = None,
) -> VerifyReport:
    """Walk compiled IR for IF completeness, orphans, dangling edges, catalog coverage."""
    if isinstance(compiled, CompileResult):
        wf = compiled.workflow
        name = wf.name
        nodes = list(wf.nodes)
        edges = list(wf.edges)
        root = wf.root_node_key
    else:
        name = str(compiled.get("name") or "unknown")
        nodes = list(compiled.get("nodes") or [])
        edges = list(compiled.get("edges") or [])
        root = str(compiled.get("root_node_key") or "root")

    report = VerifyReport(program_name=name, node_count=len(nodes), edge_count=len(edges))
    by_key = _node_map(nodes)
    keys = set(by_key)

    # Duplicate node_key
    seen: Set[str] = set()
    for n in nodes:
        k = str(_attr(n, "node_key"))
        if k in seen:
            report.findings.append(
                Finding("error", "duplicate_node_key", f"duplicate node_key={k!r}")
            )
        seen.add(k)

    if root not in keys:
        report.findings.append(
            Finding("error", "missing_root", f"root_node_key={root!r} not in nodes")
        )

    # Edge integrity (WorkflowEdgeSpec: parent_node_key, child_node_key, branch_kind)
    children_of: Dict[str, List[tuple[str, Any]]] = {k: [] for k in keys}
    for e in edges:
        parent = str(_attr(e, "parent_node_key") or "")
        child = str(_attr(e, "child_node_key") or "")
        if parent not in keys:
            report.findings.append(
                Finding("error", "dangling_parent", f"edge parent {parent!r} missing")
            )
            continue
        if child not in keys:
            report.findings.append(
                Finding("error", "dangling_child", f"edge child {child!r} missing")
            )
            continue
        children_of.setdefault(parent, []).append((child, e))

    # Reachability from root
    reachable: Set[str] = set()
    stack = [root] if root in keys else []
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        for child, _ in children_of.get(cur, []):
            stack.append(child)
    orphans = sorted(keys - reachable)
    for k in orphans:
        report.findings.append(
            Finding("error", "orphan_node", f"unreachable node_key={k!r}")
        )

    # IF: must have THEN + ELSE children (compiler emits empty ELSE SEQUENCE)
    for key, node in by_key.items():
        ntype = str(_attr(node, "node_type") or "")
        if ntype != "IF":
            continue
        kids = children_of.get(key, [])
        branches: Set[str] = set()
        for child_key, edge in kids:
            br = _attr(edge, "branch_kind") or _attr(edge, "branch")
            if br is None and isinstance(edge, Mapping):
                br = edge.get("branch_kind") or edge.get("branch")
            label = str(br or "").upper()
            if label in {"THEN", "ELSE"}:
                branches.add(label)
            elif "THEN" in label:
                branches.add("THEN")
            elif "ELSE" in label:
                branches.add("ELSE")
            else:
                ck = child_key.lower()
                if "then" in ck:
                    branches.add("THEN")
                elif "else" in ck:
                    branches.add("ELSE")
        if "THEN" not in branches:
            report.findings.append(
                Finding("error", "if_missing_then", f"IF {key!r} has no THEN branch")
            )
        if "ELSE" not in branches:
            report.findings.append(
                Finding("error", "if_missing_else", f"IF {key!r} has no ELSE branch")
            )
        if len(kids) < 2:
            report.findings.append(
                Finding(
                    "error",
                    "if_branch_count",
                    f"IF {key!r} has {len(kids)} child edge(s); expect 2 (THEN+ELSE)",
                )
            )

    # ACTION catalog coverage
    actions: List[str] = []
    for key, node in by_key.items():
        if str(_attr(node, "node_type") or "") != "ACTION":
            continue
        action = _attr(node, "action_name") or _attr(node, "action")
        if not action:
            report.findings.append(
                Finding("error", "action_missing_name", f"ACTION {key!r} has no action_name")
            )
            continue
        actions.append(str(action))
        if catalog_action_names is not None and str(action) not in catalog_action_names:
            report.findings.append(
                Finding(
                    "error",
                    "action_not_in_catalog",
                    f"ACTION {key!r} action={action!r} not in ACTION_CATALOG",
                )
            )
    report.action_names = actions

    if not any(str(_attr(n, "node_type")) == "FOREACH" for n in nodes):
        report.findings.append(
            Finding("warning", "no_foreach", "compiled workflow has no FOREACH node")
        )

    return report


def load_catalog_action_names() -> Set[str]:
    import sys

    workers = Path(__file__).resolve().parents[2] / "workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))
    from methyl_worker.action_catalog import ACTION_CATALOG

    return {e.action_name for e in ACTION_CATALOG}


def verify_program_file(path: Path | str, *, check_catalog: bool = True) -> VerifyReport:
    path = Path(path)
    compiled = compile_domain_program_file(path)
    catalog = load_catalog_action_names() if check_catalog else None
    return verify_compiled_workflow(compiled, catalog_action_names=catalog)


def verify_methylgrapher_bake(
    site: Mapping[str, Any],
    profile_action_config: Optional[Mapping[str, Any]] = None,
) -> List[Finding]:
    """Ensure methylgrapher_wgbs resolvedConfig keeps image/engine/align_engine."""
    from methyl_utils.action_config_resolver import (
        resolve_action_config,
        resolve_methylgrapher_wgbs_genome,
    )

    findings: List[Finding] = []
    merged = resolve_action_config(
        "methylgrapher_wgbs",
        site=site,
        profile_action_config=dict(profile_action_config or {}),
    )
    for key in ("image", "engine", "align_engine"):
        if merged.get(key) in (None, ""):
            findings.append(
                Finding(
                    "error",
                    "methylgrapher_bake_missing",
                    f"resolvedConfig.methylgrapher_wgbs missing {key!r} after site/profile merge",
                )
            )
    genome = resolve_methylgrapher_wgbs_genome(resolved_config=merged)
    for key in ("image", "engine", "align_engine"):
        if genome.get(key) in (None, ""):
            findings.append(
                Finding(
                    "error",
                    "methylgrapher_genome_drop",
                    f"resolve_methylgrapher_wgbs_genome dropped {key!r}",
                )
            )
    return findings


def compare_compiled_to_db_nodes(
    compiled: CompileResult | Mapping[str, Any],
    db_nodes: Iterable[Mapping[str, Any]],
) -> List[Finding]:
    """Compare compiled ACTION node_key→action_name set to DB workflow_node rows."""
    if isinstance(compiled, CompileResult):
        nodes = list(compiled.workflow.nodes)
    else:
        nodes = list(compiled.get("nodes") or [])
    want: Dict[str, str] = {}
    for n in nodes:
        if str(_attr(n, "node_type") or "") != "ACTION":
            continue
        key = str(_attr(n, "node_key"))
        action = str(_attr(n, "action_name") or _attr(n, "action") or "")
        want[key] = action
    have: Dict[str, str] = {}
    for row in db_nodes:
        if str(row.get("node_type") or "") != "ACTION":
            continue
        have[str(row["node_key"])] = str(row.get("action_name") or "")
    findings: List[Finding] = []
    for key, action in sorted(want.items()):
        if key not in have:
            findings.append(
                Finding("error", "db_missing_node", f"DB missing ACTION node_key={key!r}")
            )
        elif have[key] and have[key] != action:
            findings.append(
                Finding(
                    "error",
                    "db_action_mismatch",
                    f"node_key={key!r} git={action!r} db={have[key]!r}",
                )
            )
    for key in sorted(set(have) - set(want)):
        findings.append(
            Finding("warning", "db_extra_node", f"DB has extra ACTION node_key={key!r}")
        )
    return findings


def report_to_json(report: VerifyReport) -> str:
    return json.dumps(report.to_dict(), indent=2) + "\n"
