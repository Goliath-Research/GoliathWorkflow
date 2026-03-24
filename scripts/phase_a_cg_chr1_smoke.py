#!/usr/bin/env python3
"""
Phase A smoke test: CG context, one chromosome (default ``1``), from ``project_Healthy_vs_PCa1-4_CG.json``.

Writes a temporary project JSON (narrowed ``chromosomes`` / ``contexts``, optional path overrides),
then runs:

1. ``methyl-centroid --project <tmp> --group all``
2. ``methyl-detector --project <tmp> --per-cancer-group`` (optionally a single ``--group`` stage)

Use ``--output-base`` when the paths in the JSON point at another machine (e.g. ``/work/...``).

Examples (repo root, venv active)::

    python scripts/phase_a_cg_chr1_smoke.py \\
        --output-base /data/my_run/Healthy_vs_PCa1-4-CG

    # Centroids already built; only detector for one stage (label must match project comparisons, e.g. pca_pca2)
    python scripts/phase_a_cg_chr1_smoke.py --output-base ... --skip-centroid --detector-group pca_pca2

    # All disease stages (healthy vs pca_pca1 … pca_pca4)
    python scripts/phase_a_cg_chr1_smoke.py --output-base ... --all-disease-stages
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from methyl_utils import load_project


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = REPO_ROOT / "configs" / "project_Healthy_vs_PCa1-4_CG.json"


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def build_phase_a_project(
    base_project: Path,
    *,
    chromosome: str,
    context: str,
    output_base: Optional[str],
    samples_base_path: Optional[str],
    keep_filter_funnel: bool,
    no_gpu_centroid: bool,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (full_project_dict, centroid_step_override_dict)."""
    data = json.loads(base_project.read_text(encoding="utf-8"))
    data["chromosomes"] = [chromosome]
    data["contexts"] = [context]
    if output_base is not None:
        data["output_base"] = output_base
    if samples_base_path is not None:
        data["samples_base_path"] = samples_base_path

    if not keep_filter_funnel:
        sc = data.setdefault("step_config", {})
        det = sc.setdefault("detection", {})
        det.pop("filter_funnel_explore", None)

    centroid_override: Dict[str, Any] = {}
    if no_gpu_centroid:
        centroid_override = {"base_config": {"use_gpu": False}}

    return data, centroid_override


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def run_cmd(argv: List[str], *, cwd: Optional[Path] = None) -> None:
    print("\n→", " ".join(argv), flush=True)
    subprocess.run(argv, check=True, cwd=cwd)


def verify_dual_exports(
    project_json: Path,
    *,
    output_base: Optional[str],
    control_label: str,
    disease_label: str,
    chromosome: str,
) -> List[str]:
    """Return list of warnings (empty if checks pass)."""
    proj = load_project(project_json, output_base_override=output_base)
    det_dir = Path(proj.get_detection_output_dir(control_label, disease_label))
    warnings: List[str] = []
    disc = det_dir / f"dmps-{chromosome}-discovery.csv"
    clf = det_dir / f"dmps-{chromosome}-classifier.csv"
    meta = det_dir / f"dmp-export-{chromosome}.meta.json"
    ctx = (proj.contexts or ["CG"])[0]
    pkl = det_dir / f"classifier-{chromosome}-{ctx}.pkl"
    for p, name in [
        (disc, "discovery CSV"),
        (clf, "classifier CSV"),
        (meta, "branch metadata JSON"),
        (pkl, "classifier pickle"),
    ]:
        if not p.is_file():
            warnings.append(f"missing {name}: {p}")
    return warnings


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--project",
        type=Path,
        default=DEFAULT_PROJECT,
        help=f"Base project JSON (default: {DEFAULT_PROJECT})",
    )
    p.add_argument(
        "--output-base",
        type=str,
        default=None,
        help="Override project output_base (recommended if JSON paths are on another host)",
    )
    p.add_argument(
        "--samples-base-path",
        type=str,
        default=None,
        help="Override samples_base_path for this run",
    )
    p.add_argument("--chromosome", "-C", default="1", help='Single chromosome to process (default: "1")')
    p.add_argument("--context", "-x", default="CG", choices=["CG", "CHG", "CHH"], help="Single context (default: CG)")
    p.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Directory for generated JSON overrides (default: <repo>/.phase_a_cg_chr1)",
    )
    p.add_argument("--skip-centroid", action="store_true", help="Skip methyl-centroid (centroids already built)")
    p.add_argument("--skip-detector", action="store_true", help="Skip methyl-detector")
    p.add_argument(
        "--detector-group",
        type=str,
        default=None,
        metavar="LABEL",
        help="methyl-detector --group disease label (must match project comparisons, e.g. pca_pca1). "
        "Default: first comparison from the project JSON.",
    )
    p.add_argument(
        "--all-disease-stages",
        action="store_true",
        help="Run detector for every comparison (pca1–pca4), not just --detector-group",
    )
    p.add_argument(
        "--keep-filter-funnel",
        action="store_true",
        help="Keep step_config.detection.filter_funnel_explore (slower; default: drop for smoke)",
    )
    p.add_argument(
        "--no-gpu-centroid",
        action="store_true",
        help="Pass use_gpu: false in centroid step override",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only write JSON files and print commands; do not execute pipelines",
    )
    args = p.parse_args()

    if not args.project.is_file():
        print(f"Project file not found: {args.project}", file=sys.stderr)
        return 2

    work_dir = args.work_dir or (REPO_ROOT / ".phase_a_cg_chr1")
    work_dir = work_dir.resolve()

    data, centroid_ov = build_phase_a_project(
        args.project,
        chromosome=args.chromosome,
        context=args.context,
        output_base=args.output_base,
        samples_base_path=args.samples_base_path,
        keep_filter_funnel=args.keep_filter_funnel,
        no_gpu_centroid=args.no_gpu_centroid,
    )

    phase_project_path = work_dir / "phase_a_project_CG_chr1.json"
    write_json(phase_project_path, data)

    resolved_detector_group: Optional[str] = None
    if not args.all_disease_stages:
        if args.detector_group is not None:
            resolved_detector_group = args.detector_group.strip()
        else:
            comps = load_project(phase_project_path, output_base_override=args.output_base).get_comparisons()
            if not comps:
                print("No comparisons in project; pass --detector-group explicitly.", file=sys.stderr)
                return 2
            resolved_detector_group = comps[0].disease_group

    centroid_override_path: Optional[Path] = None
    if centroid_ov:
        centroid_override_path = work_dir / "phase_a_centroid_override.json"
        write_json(centroid_override_path, centroid_ov)

    venv_bin = REPO_ROOT / ".venv" / "bin"
    centroid_exe = venv_bin / "methyl-centroid"
    detector_exe = venv_bin / "methyl-detector"
    if not centroid_exe.is_file():
        centroid_exe = Path("methyl-centroid")
    if not detector_exe.is_file():
        detector_exe = Path("methyl-detector")

    centroid_cmd = [str(centroid_exe), "--project", str(phase_project_path), "--group", "all"]
    if centroid_override_path:
        centroid_cmd += ["--step-override", str(centroid_override_path)]

    detector_cmd = [str(detector_exe), "--project", str(phase_project_path)]
    if args.output_base:
        detector_cmd += ["--output-base", args.output_base]
    if args.all_disease_stages:
        detector_cmd.append("--per-cancer-group")
    else:
        detector_cmd += ["--group", resolved_detector_group]

    print("Phase A project written:", phase_project_path)
    print("  chromosomes:", data.get("chromosomes"))
    print("  contexts:", data.get("contexts"))
    print("  output_base:", data.get("output_base"))
    if centroid_override_path:
        print("  centroid override:", centroid_override_path)
    if resolved_detector_group is not None:
        print("  methyl-detector --group:", resolved_detector_group)

    if args.dry_run:
        print("\n[dry-run] Would run:")
        if not args.skip_centroid:
            print(" ", " ".join(centroid_cmd))
        if not args.skip_detector:
            print(" ", " ".join(detector_cmd))
        return 0

    env = os.environ.copy()
    # Ensure local packages resolve when not using editable installs from cwd
    py_path = env.get("PYTHONPATH", "")
    extra = ":".join(
        str(REPO_ROOT / "packages" / name)
        for name in ("methylutils", "methylcentroid", "methyldetector", "methylclassifier")
    )
    env["PYTHONPATH"] = extra + (":" + py_path if py_path else "")

    try:
        if not args.skip_centroid:
            run_cmd(centroid_cmd, cwd=REPO_ROOT)
        if not args.skip_detector:
            run_cmd(detector_cmd, cwd=REPO_ROOT)
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}", file=sys.stderr)
        return e.returncode or 1

    if not args.skip_detector:
        proj = load_project(phase_project_path, output_base_override=args.output_base)
        comparisons = proj.get_comparisons()
        stages = (
            [resolved_detector_group]
            if not args.all_disease_stages and resolved_detector_group is not None
            else [spec.disease_group for spec in comparisons]
        )
        print("\nDual-export checks:")
        for stage in stages:
            spec = next((c for c in comparisons if c.disease_group == stage), None)
            ctrl = spec.control_group if spec is not None else (
                proj.control.groups[0].label if proj.control and proj.control.groups else "healthy"
            )
            w = verify_dual_exports(
                phase_project_path,
                output_base=args.output_base,
                control_label=ctrl,
                disease_label=stage,
                chromosome=args.chromosome,
            )
            prefix = f"  {ctrl} vs {stage}: "
            if w:
                for line in w:
                    print(prefix + line)
            else:
                print(prefix + "ok (discovery + classifier CSV + meta + pickle present)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
