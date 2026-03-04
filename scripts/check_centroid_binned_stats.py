#!/usr/bin/env python3
"""Check if a centroid H5 file has binned_stats (for MethylDetector ECDF)."""
import sys
from pathlib import Path

from methyl_utils import MethylSample


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python scripts/check_centroid_binned_stats.py <path-to-centroid.h5>")
        print("Example: python scripts/check_centroid_binned_stats.py /path/to/1-CG.h5")
        sys.exit(1)
    p = Path(path)
    if not p.exists():
        print(f"File not found: {p}")
        sys.exit(1)
    c = MethylSample.load_from_h5(str(p))
    bs = getattr(c, "binned_stats", None)
    ok = bs is not None and "bin_edges" in (bs or {}) and "bin_counts" in (bs or {})
    print(f"binned_stats present: {ok}")
    if bs:
        print(f"  bin_edges length: {len(bs.get('bin_edges', []))}")
        print(f"  bin_counts shape: {getattr(bs.get('bin_counts'), 'shape', 'N/A')}")


if __name__ == "__main__":
    main()
