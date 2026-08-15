#!/usr/bin/env python3
"""Write a multi-arm comparison report under /work/samples/_comparisons/<stamp>/.

Does not run aligners — stages dirs and records metrics supplied via JSON or
discovered BAM flagstat. Originals (Clara / vg / MethylDackel) stay selectable.

Example:

  .venv/bin/python scripts/comparison_arms_report.py \\
    --sample-id S1 \\
    --samples-base /work/samples \\
    --ensure-arms \\
    --arm-metric align.linear.parabricks:status=staged \\
    --arm-metric align.linear.mojo:status=staged \\
    --note "Dirs created; run SamplePrep per arm with build_align_arm_start_payload"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "methylutils"))

from methyl_utils.testing.sample_prep_mode_compare import (  # noqa: E402
    COMPARE_ALIGN_ARMS,
    ensure_comparison_arms,
    ensure_comparison_report_dir,
    sample_root_dir,
    write_comparison_arms_report,
)


def _parse_arm_metric(raw: str) -> tuple[str, Dict[str, Any]]:
    # arm:key=val,key=val
    if ":" not in raw:
        raise SystemExit(f"expected arm:key=val[,key=val]: {raw}")
    arm, rest = raw.split(":", 1)
    metrics: Dict[str, Any] = {}
    if rest:
        for part in rest.split(","):
            if not part:
                continue
            if "=" not in part:
                metrics[part] = True
                continue
            k, v = part.split("=", 1)
            try:
                metrics[k] = json.loads(v)
            except json.JSONDecodeError:
                metrics[k] = v
    return arm, metrics


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample-id", required=True)
    ap.add_argument("--samples-base", default="/work/samples")
    ap.add_argument("--stamp", default=None)
    ap.add_argument(
        "--ensure-arms",
        action="store_true",
        help=f"Create {', '.join(COMPARE_ALIGN_ARMS)} (+ extract dirs if listed)",
    )
    ap.add_argument(
        "--arms",
        nargs="*",
        default=None,
        help="Subset of align/extract arm ids (default: all align arms)",
    )
    ap.add_argument(
        "--arm-metric",
        action="append",
        default=[],
        help="arm:key=val[,key=val] (repeatable)",
    )
    ap.add_argument("--note", action="append", default=[])
    ap.add_argument(
        "--methyldackel-manifest",
        default=None,
        help="Path to extract.methyldackel/methyldackel_manifest.json",
    )
    ap.add_argument(
        "--gates-json",
        default=None,
        help="JSON object of gate name → {status, detail}",
    )
    args = ap.parse_args()

    root = sample_root_dir(args.samples_base, args.sample_id)
    if args.ensure_arms:
        ensure_comparison_arms(
            root,
            sample_id=args.sample_id,
            arms=args.arms,
            link_fastqs=root.is_dir(),
        )

    arms: Dict[str, Dict[str, Any]] = {}
    for raw in args.arm_metric:
        arm, metrics = _parse_arm_metric(raw)
        arms.setdefault(arm, {}).update(metrics)
    if not arms and args.arms:
        for arm in args.arms:
            arms[arm] = {"status": "staged"}
    if not arms:
        for arm in COMPARE_ALIGN_ARMS:
            if arm.startswith("align."):
                arms[arm] = {"status": "staged", "sample_dir": str(root / arm)}

    gates = None
    if args.gates_json:
        gates = json.loads(Path(args.gates_json).read_text(encoding="utf-8"))

    md = None
    if args.methyldackel_manifest:
        md = json.loads(Path(args.methyldackel_manifest).read_text(encoding="utf-8"))

    report_dir = ensure_comparison_report_dir(args.samples_base, stamp=args.stamp)
    json_path, md_path = write_comparison_arms_report(
        report_dir,
        sample_id=args.sample_id,
        arms=arms,
        gates=gates,
        notes=args.note
        or [
            "Clara / vg / optional MethylDackel retained for before/after.",
            "Do not flip production site defaults from this harness.",
        ],
        methyldackel=md,
    )
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
