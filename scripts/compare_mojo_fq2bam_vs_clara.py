#!/usr/bin/env python3
"""Compare MojoFq2bamMeth vs Clara fq2bam_meth flagstat mapped-rate for concordance gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _flagstat_mapped_rate(bam: Path) -> float:
    proc = subprocess.run(
        ["samtools", "flagstat", str(bam)],
        capture_output=True,
        text=True,
        check=True,
    )
    total = mapped = 0
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 1:
            continue
        try:
            n = int(parts[0])
        except ValueError:
            continue
        if "in total" in line:
            total = n
        elif "mapped (" in line:
            mapped = n
    if total <= 0:
        raise RuntimeError(f"no total reads in flagstat for {bam}")
    return mapped / total


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clara-dir", type=Path, required=True)
    p.add_argument("--mojo-dir", type=Path, required=True)
    p.add_argument("--sample-id", required=True)
    p.add_argument("--max-delta", type=float, default=0.02)
    args = p.parse_args(argv)

    clara_bam = args.clara_dir / f"{args.sample_id}.bam"
    mojo_bam = args.mojo_dir / f"{args.sample_id}.bam"
    for bam in (clara_bam, mojo_bam):
        if not bam.is_file():
            print(f"missing BAM: {bam}", file=sys.stderr)
            return 2

    r_clara = _flagstat_mapped_rate(clara_bam)
    r_mojo = _flagstat_mapped_rate(mojo_bam)
    delta = abs(r_clara - r_mojo)
    report = {
        "sampleId": args.sample_id,
        "clara_mapped_rate": r_clara,
        "mojo_mapped_rate": r_mojo,
        "abs_delta": delta,
        "max_delta": args.max_delta,
        "pass": delta <= args.max_delta,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
