#!/usr/bin/env python3
"""Audit CAAS skip rates and empty-artifact centroid commits for a study tree.

Usage:
  source .venv/bin/activate
  python scripts/audit_caas_skip_rate.py /work/projects/<study>/<project_name>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            yield row


def _scan_action_run_logs(root: Path) -> Tuple[Counter, Counter, int]:
    """Return (action_counts, skipped_counts, total_rows)."""
    actions: Counter = Counter()
    skipped: Counter = Counter()
    total = 0
    for log in root.rglob("action_run_log.jsonl"):
        for row in _iter_jsonl(log):
            name = str(row.get("action_name") or row.get("capability") or "unknown")
            actions[name] += 1
            total += 1
            status = str(row.get("status") or "").lower()
            if row.get("skipped") is True or status == "skipped":
                skipped[name] += 1
    return actions, skipped, total


def _scan_caas_manifests(caas_root: Path) -> Dict[str, Any]:
    empty_required = 0
    nonempty = 0
    by_action: Counter = Counter()
    empty_centroid_examples: List[str] = []
    if not caas_root.is_dir():
        return {
            "entries": 0,
            "empty_artifact_required": 0,
            "by_action": {},
            "empty_centroid_examples": [],
        }
    for manifest in caas_root.glob("*/*/manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        action = str(data.get("action_name") or manifest.parent.parent.name)
        by_action[action] += 1
        arts = data.get("artifacts") or []
        product = [
            a
            for a in arts
            if isinstance(a, dict)
            and ".action_results" not in str(a.get("path") or "")
        ]
        if product:
            nonempty += 1
            continue
        # Centroid (and other product actions) with empty artifact lists are wasted.
        if action in {"pipeline.centroid", "pipeline_centroid"} or "centroid" in action:
            empty_required += 1
            if len(empty_centroid_examples) < 5:
                empty_centroid_examples.append(str(manifest))
    return {
        "entries": nonempty + empty_required,
        "nonempty_artifacts": nonempty,
        "empty_artifact_required": empty_required,
        "by_action": dict(by_action),
        "empty_centroid_examples": empty_centroid_examples,
    }


def _scan_foreach_bundles(caas_root: Path) -> int:
    bundle = caas_root / "foreach_bundle"
    if not bundle.is_dir():
        return 0
    return sum(1 for _ in bundle.glob("*/manifest.json"))


def audit_study(project_root: Path) -> Dict[str, Any]:
    actions, skipped, total = _scan_action_run_logs(project_root)
    caas = project_root / ".caas"
    caas_stats = _scan_caas_manifests(caas)
    skip_rate = (sum(skipped.values()) / total) if total else 0.0
    per_action = []
    for name, count in sorted(actions.items()):
        sk = skipped.get(name, 0)
        per_action.append(
            {
                "action": name,
                "total": count,
                "skipped": sk,
                "skip_rate": (sk / count) if count else 0.0,
            }
        )
    return {
        "project_root": str(project_root),
        "action_log_rows": total,
        "skipped_rows": sum(skipped.values()),
        "overall_skip_rate": skip_rate,
        "per_action": per_action,
        "caas": caas_stats,
        "foreach_bundle_entries": _scan_foreach_bundles(caas),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "project_root",
        type=Path,
        help="Study project root (contains .caas/ and monte_carlo_runs/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full JSON report",
    )
    args = parser.parse_args(argv)
    root = args.project_root.expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    report = audit_study(root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(f"project_root: {report['project_root']}")
    print(
        f"action_log_rows: {report['action_log_rows']}  "
        f"skipped: {report['skipped_rows']}  "
        f"skip_rate: {report['overall_skip_rate']:.1%}"
    )
    print(
        f"caas entries: {report['caas'].get('entries', 0)}  "
        f"empty-artifact centroids: {report['caas'].get('empty_artifact_required', 0)}  "
        f"foreach_bundle: {report['foreach_bundle_entries']}"
    )
    print("top actions by skip_rate:")
    ranked = sorted(
        report["per_action"],
        key=lambda r: (-r["skip_rate"], -r["total"]),
    )[:15]
    for row in ranked:
        if row["total"] == 0:
            continue
        print(
            f"  {row['action']}: {row['skipped']}/{row['total']} "
            f"({row['skip_rate']:.1%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
