#!/usr/bin/env python3
"""Micro-benchmark CPU vs GPU ECDF-first kernels."""

from __future__ import annotations

import argparse
import time

import numpy as np

from methyl_utils.array_backend import prefer_gpu_default
from methyl_utils.statistical_tests import (
    ecdf_bhattacharyya_trapezoidal_from_bin_counts,
    mann_whitney_from_bin_counts,
)


def _bench(fn, repeats: int = 5) -> float:
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return float(np.median(times))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-pos", type=int, default=50_000)
    parser.add_argument("--n-bins", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    rng = np.random.default_rng(42)
    n_pos, n_bins = args.n_pos, args.n_bins
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bc1 = rng.integers(1, 100, size=(n_pos, n_bins)).astype(np.float64)
    bc2 = rng.integers(1, 100, size=(n_pos, n_bins)).astype(np.float64)
    n1 = rng.integers(50, 500, size=n_pos).astype(np.float64)
    n2 = rng.integers(50, 500, size=n_pos).astype(np.float64)

    print(f"n_positions={n_pos:,} n_bins={n_bins} gpu_available={prefer_gpu_default()}")

    mw_cpu = _bench(
        lambda: mann_whitney_from_bin_counts(bc1, bc2, n1, n2, prefer_gpu=False),
        args.repeats,
    )
    print(f"mann_whitney CPU: {mw_cpu:.4f}s")

    if prefer_gpu_default():
        mw_gpu = _bench(
            lambda: mann_whitney_from_bin_counts(bc1, bc2, n1, n2, prefer_gpu=True),
            args.repeats,
        )
        print(f"mann_whitney GPU: {mw_gpu:.4f}s  speedup={mw_cpu/mw_gpu:.2f}x")

    bh_cpu = _bench(
        lambda: ecdf_bhattacharyya_trapezoidal_from_bin_counts(
            bc1, bc2, bin_edges, prefer_gpu=False
        ),
        args.repeats,
    )
    print(f"bhattacharyya CPU: {bh_cpu:.4f}s")

    if prefer_gpu_default():
        bh_gpu = _bench(
            lambda: ecdf_bhattacharyya_trapezoidal_from_bin_counts(
                bc1, bc2, bin_edges, prefer_gpu=True
            ),
            args.repeats,
        )
        print(f"bhattacharyya GPU: {bh_gpu:.4f}s  speedup={bh_cpu/bh_gpu:.2f}x")


if __name__ == "__main__":
    main()
