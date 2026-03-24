#!/usr/bin/env python3
"""
Label DMP sites across stage-wise detection folders (discovery branch CSVs).

Reads ``dmps-*-discovery.csv`` when present, otherwise non-discovery ``dmps-*.csv``
from each ``--stage <label> <detection_dir>`` pair. Emits a BED-like CSV with:

- ``core``: site present in every stage
- ``stage_specific_<label>``: present in exactly one stage
- ``partial``: present in more than one stage but not all

Usage (from repo root with venv activated)::

    PYTHONPATH=packages/methylutils python scripts/dmp_progression_categories.py \\
        --stage pca1 /path/to/detections/healthy/pca1 \\
        --stage pca2 /path/to/detections/healthy/pca2 \\
        -o progression_labels.csv

Requires: pandas
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

Site = Tuple[str, str, int]


def _parse_stages(spec: List[str]) -> List[Tuple[str, Path]]:
    if len(spec) % 2 != 0:
        raise ValueError("--stage requires label path pairs")
    out = []
    for i in range(0, len(spec), 2):
        out.append((spec[i], Path(spec[i + 1]).resolve()))
    return out


def _discovery_csvs(det_dir: Path) -> List[Path]:
    try:
        from methyl_utils.dmp_export_paths import find_discovery_dmps_csvs

        return find_discovery_dmps_csvs(det_dir)
    except ImportError:
        disc = sorted(det_dir.glob("dmps-*-discovery.csv"))
        if disc:
            return disc
        return [p for p in sorted(det_dir.glob("dmps-*.csv")) if "-classifier" not in p.stem]


def _sites_from_dir(det_dir: Path) -> Set[Site]:
    keys: Set[Site] = set()
    for csv_path in _discovery_csvs(det_dir):
        import pandas as pd

        df = pd.read_csv(csv_path)
        need = {"chromosome", "context", "position"}
        if not need.issubset(df.columns):
            continue
        for _, r in df.iterrows():
            keys.add((str(r["chromosome"]), str(r["context"]), int(r["position"])))
    return keys


def _site_rows(
    stage_to_sites: Dict[str, Set[Site]],
) -> List[dict]:
    import pandas as pd

    all_labels = list(stage_to_sites.keys())
    n_stages = len(all_labels)
    union: Set[Site] = set()
    for s in stage_to_sites.values():
        union |= s

    rows = []
    for site in sorted(union):
        chrom, ctx, pos = site
        present = [lbl for lbl in all_labels if site in stage_to_sites[lbl]]
        np = len(present)
        if np == n_stages:
            cat = "core"
        elif np == 1:
            cat = f"stage_specific_{present[0]}"
        else:
            cat = "partial"
        rows.append(
            {
                "chromosome": chrom,
                "context": ctx,
                "position": pos,
                "category": cat,
                "n_stages": np,
                "stages": ",".join(sorted(present)),
            }
        )
    return rows


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--stage",
        action="append",
        nargs=2,
        metavar=("LABEL", "DIR"),
        required=True,
        help="Disease stage label and MethylDetector output directory for that comparison",
    )
    p.add_argument("-o", "--output", type=Path, required=True, help="Output CSV path")
    args = p.parse_args(list(argv) if argv is not None else None)

    stage_to_sites: Dict[str, Set[Site]] = {}
    for label, dpath in args.stage:
        det_dir = Path(dpath).resolve()
        if not det_dir.is_dir():
            print(f"Not a directory: {det_dir}", file=sys.stderr)
            return 2
        stage_to_sites[label] = _sites_from_dir(det_dir)
        if not stage_to_sites[label]:
            print(f"Warning: no DMP sites loaded from {det_dir}", file=sys.stderr)

    import pandas as pd

    rows = _site_rows(stage_to_sites)
    if not rows:
        print("No sites in union; check paths and CSV columns.", file=sys.stderr)
        return 3
    out = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"Wrote {len(out)} sites to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
