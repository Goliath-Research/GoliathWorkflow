#!/usr/bin/env python3
"""Relocate sample-root Clara products into ``align.linear.parabricks/``.

Use after a SamplePrep instance that wrote ``{id}.bam`` / ``{id}.qc-metrics.tar``
at ``/work/samples/{id}/`` instead of the documented arm leaf. Does **not**
delete existing ``align.*`` / ``extract.*`` trees. Skips a file when the
destination already exists. FASTQs and ``.caas/`` stay at the sample root.

Does not retarget a live workflow instance. Run only after that instance finishes.

Example (dry-run):

  .venv/bin/python scripts/relocate_root_clara_products.py \\
    --samples-base /tmp/samples-copy --sample-id S1

Example (apply + manifest, after the instance has finished):

  .venv/bin/python scripts/relocate_root_clara_products.py \\
    --samples-base /tmp/samples-copy --apply --manifest /tmp/relocate.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "methylutils"))

from methyl_utils.sample_arm_layout import (  # noqa: E402
    is_mode_leaf_dirname,
    sample_root_dir,
)

CLARA_LINEAR_ARM = "align.linear.parabricks"

_PRODUCT_SUFFIXES = (
    ".bam",
    ".bam.bai",
    ".qc-metrics.tar",
    ".json",
    ".deduplicate_metrics.txt",
    ".fq2bam_meth.log",
    ".alignment_qc.json",
    ".extraction_manifest.json",
    ".extraction_qc.json",
    ".methyl_extract.log",
)

_H5_SUFFIX = ".h5"


def _is_clara_like_root_product(path: Path, sample_id: str) -> bool:
    name = path.name
    if name.startswith(".") or is_mode_leaf_dirname(name):
        return False
    if name.endswith(_H5_SUFFIX):
        return True
    if name.startswith(f"{sample_id}.") or name.startswith(f"{sample_id}-"):
        return name.endswith(_PRODUCT_SUFFIXES) or name.endswith(_H5_SUFFIX)
    # Per-chrom extract matrices: 1-CG.h5
    if name.endswith(_H5_SUFFIX) and "-" in name:
        return True
    return False


def iter_sample_roots(samples_base: Path, sample_ids: Optional[Sequence[str]]) -> List[Path]:
    if sample_ids:
        return [sample_root_dir(samples_base, sid) for sid in sample_ids]
    if not samples_base.is_dir():
        return []
    out: List[Path] = []
    for path in sorted(samples_base.iterdir()):
        if not path.is_dir() or path.name.startswith("_") or path.name.startswith("."):
            continue
        if is_mode_leaf_dirname(path.name):
            continue
        out.append(path)
    return out


def relocate_sample_root(
    sample_root: Path,
    *,
    dry_run: bool = True,
    arm: str = CLARA_LINEAR_ARM,
) -> Dict[str, Any]:
    sample_id = sample_root.name
    dest_dir = sample_root / arm
    record: Dict[str, Any] = {
        "sampleId": sample_id,
        "sampleRoot": str(sample_root),
        "destDir": str(dest_dir),
        "moved": [],
        "skipped": [],
        "missing": False,
    }
    if not sample_root.is_dir():
        record["missing"] = True
        return record
    candidates: List[Path] = []
    for path in sorted(sample_root.iterdir()):
        if path.is_dir():
            continue
        if not path.is_file():
            continue
        if path.suffix in {".gz"} and "fastq" in path.name.lower():
            continue
        if _is_clara_like_root_product(path, sample_id):
            candidates.append(path)
    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(candidates):
        dest = dest_dir / src.name
        entry = {"src": str(src), "dest": str(dest)}
        if dest.exists() or dest.is_symlink():
            record["skipped"].append({**entry, "reason": "destination_exists"})
            continue
        if dry_run:
            record["moved"].append({**entry, "dryRun": True})
            continue
        shutil.move(str(src), str(dest))
        record["moved"].append(entry)
    return record


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples-base",
        required=True,
        help="Sample identity roots (required; do not point at a live /work/samples tree while SamplePrep is running).",
    )
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="Limit to one sample id (repeatable). Default: every sample root.",
    )
    parser.add_argument(
        "--arm",
        default=CLARA_LINEAR_ARM,
        help="Destination arm directory name (default: align.linear.parabricks).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move files. Default is dry-run (print/write a manifest only).",
    )
    parser.add_argument(
        "--allow-work-samples",
        action="store_true",
        help="Permit --samples-base /work/samples (refused by default while instance 67 may be live).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Deprecated alias for the default dry-run.")
    parser.add_argument("--manifest", type=str, default="")
    args = parser.parse_args(list(argv) if argv is not None else None)

    samples_base = Path(args.samples_base).expanduser().resolve()
    work_samples = Path("/work/samples").expanduser().resolve()
    if samples_base == work_samples and not args.allow_work_samples:
        print(
            "Refusing /work/samples without --allow-work-samples "
            "(do not relocate a live SamplePrep cohort).",
            file=sys.stderr,
        )
        return 2
    dry_run = not args.apply
    rows = [
        relocate_sample_root(root, dry_run=dry_run, arm=args.arm)
        for root in iter_sample_roots(samples_base, args.sample_ids)
    ]
    payload = {
        "schema": "methylpipeline.relocate_root_clara_products",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "samples_base": str(samples_base),
        "dry_run": dry_run,
        "arm": args.arm,
        "samples": rows,
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.manifest:
        Path(args.manifest).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
