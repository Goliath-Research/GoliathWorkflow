#!/usr/bin/env python3
"""
Verify every sample under /work/samples/<sample_id>/ has the expected H5 extracts.

Autosomes 1–22 are always required ({chrom}-CG.h5 by default). Sex chromosomes
are inferred per sample (shared pool across diseases):

  - Y present  → require X and Y (typical male)
  - X only     → require X only (typical female); missing Y is OK
  - neither    → incomplete

Usage:
  python scripts/check_sample_h5_coverage.py
  python scripts/check_sample_h5_coverage.py --samples-base /work/samples --report /tmp/sample_h5.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Sequence

AUTOSOMES: List[str] = [str(i) for i in range(1, 23)]
DEFAULT_CONTEXT = "CG"
DEFAULT_SAMPLES_BASE = "/work/samples"
SexChromMode = Literal["auto", "both", "any"]


@dataclass(frozen=True)
class SampleCheckResult:
    sample_id: str
    sample_dir: Path
    sex_profile: str
    expected: int
    found: int
    missing: List[str]

    @property
    def complete(self) -> bool:
        return len(self.missing) == 0 and self.expected > 0


def h5_name(chrom: str, context: str) -> str:
    return f"{chrom}-{context}.h5"


def _autosome_names(context: str) -> List[str]:
    return [h5_name(c, context) for c in AUTOSOMES]


def check_sample_dir(
    sample_dir: Path,
    context: str,
    *,
    sex_mode: SexChromMode,
) -> SampleCheckResult:
    ctx = context.strip() or DEFAULT_CONTEXT
    x_name = h5_name("X", ctx)
    y_name = h5_name("Y", ctx)
    has_x = (sample_dir / x_name).is_file()
    has_y = (sample_dir / y_name).is_file()
    auto_names = _autosome_names(ctx)

    if sex_mode == "both":
        required = [*auto_names, x_name, y_name]
        profile = "n/a"
    elif sex_mode == "any":
        required = [*auto_names, x_name, y_name]
        profile = "unknown"
    elif has_y:
        required = [*auto_names, x_name, y_name]
        profile = "male"
    elif has_x:
        required = [*auto_names, x_name]
        profile = "female"
    else:
        required = list(auto_names)
        profile = "unknown"

    missing = [n for n in required if not (sample_dir / n).is_file()]

    if sex_mode == "any":
        auto_missing = [m for m in missing if m in auto_names]
        if auto_missing:
            missing = auto_missing
        elif not (has_x or has_y):
            missing = [f"at least one of {x_name}, {y_name}"]
        else:
            missing = []
            profile = "male" if has_y else "female"

    elif sex_mode == "auto" and profile == "unknown":
        auto_missing = [m for m in missing if m in auto_names]
        if not has_x and not has_y:
            missing = [*auto_missing, f"at least one of {x_name}, {y_name}"]
        elif has_y and not has_x:
            missing = [x_name]
            profile = "male"
        else:
            missing = auto_missing

    expected = len(AUTOSOMES)
    if profile == "male":
        expected += 2
    elif profile == "female":
        expected += 1
    elif sex_mode == "both":
        expected = len(required)

    found = (
        sum(1 for n in auto_names if (sample_dir / n).is_file())
        + (1 if has_x else 0)
        + (1 if has_y else 0)
    )

    return SampleCheckResult(
        sample_id=sample_dir.name,
        sample_dir=sample_dir,
        sex_profile=profile,
        expected=expected,
        found=found,
        missing=missing,
    )


def list_sample_dirs(samples_base: Path) -> List[Path]:
    if not samples_base.is_dir():
        raise FileNotFoundError(f"samples base not found: {samples_base}")
    return sorted(
        (p.resolve() for p in samples_base.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )


def write_report(path: Path, results: Sequence[SampleCheckResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "sample_id",
                "sample_dir",
                "sex_profile",
                "status",
                "expected_h5",
                "found_h5",
                "missing_count",
                "missing_h5",
            ]
        )
        for r in results:
            w.writerow(
                [
                    r.sample_id,
                    str(r.sample_dir),
                    r.sex_profile,
                    "complete" if r.complete else "incomplete",
                    r.expected,
                    r.found,
                    len(r.missing),
                    ";".join(r.missing),
                ]
            )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Check all sample folders under /work/samples for valid per-chromosome H5 files.",
    )
    p.add_argument(
        "--samples-base",
        default=DEFAULT_SAMPLES_BASE,
        help=f"Directory containing one folder per sample (default: {DEFAULT_SAMPLES_BASE})",
    )
    p.add_argument(
        "--context",
        default=DEFAULT_CONTEXT,
        help=f"H5 suffix context (default: {DEFAULT_CONTEXT})",
    )
    p.add_argument(
        "--sex-chromosomes-mode",
        choices=("auto", "both", "any"),
        default="auto",
        help="auto: infer male (X+Y) vs female (X only); both: always X+Y; any: X or Y (default: auto)",
    )
    p.add_argument(
        "--report",
        type=Path,
        help="Write CSV report to this path",
    )
    p.add_argument(
        "--show-missing-limit",
        type=int,
        default=8,
        help="Max missing files listed per incomplete sample (default: 8)",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    samples_base = Path(args.samples_base).expanduser().resolve()
    sex_mode: SexChromMode = args.sex_chromosomes_mode

    sample_dirs = list_sample_dirs(samples_base)
    if not sample_dirs:
        print(f"No sample directories under {samples_base}", file=sys.stderr)
        return 2

    results = [check_sample_dir(d, args.context, sex_mode=sex_mode) for d in sample_dirs]
    complete = [r for r in results if r.complete]
    incomplete = [r for r in results if not r.complete]
    profiles: dict[str, int] = {}
    for r in complete:
        profiles[r.sex_profile] = profiles.get(r.sex_profile, 0) + 1

    print(f"Samples base: {samples_base}")
    print(f"Samples checked: {len(results)}")
    print(f"Context: {args.context}  Sex chromosomes: {sex_mode}")
    print(f"Autosomes required: 1–22")
    print(f"Complete: {len(complete)}  Incomplete: {len(incomplete)}")
    if profiles:
        print("Complete by profile: " + ", ".join(f"{k}={v}" for k, v in sorted(profiles.items())))

    limit = max(0, int(args.show_missing_limit))
    for r in incomplete:
        print(
            f"\nINCOMPLETE  {r.sample_id}  profile={r.sex_profile}  "
            f"({r.found}/{r.expected})  {r.sample_dir}"
        )
        for name in r.missing[:limit]:
            print(f"  missing: {name}")
        if limit and len(r.missing) > limit:
            print(f"  ... and {len(r.missing) - limit} more")

    if args.report:
        write_report(args.report, results)
        print(f"\nWrote report: {args.report}")

    return 1 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
