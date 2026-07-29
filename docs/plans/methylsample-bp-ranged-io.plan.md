---
name: MethylSample bp-ranged I/O
overview: "Add genomic bp-ranged I/O to MethylSample/MethylFrame H5 loading: resolve [start_bp, end_bp) to a contiguous row slice on sorted pos, preserving per-CpG rows. No window aggregation."

> **Status: IMPLEMENTED.** API in [`packages/methylutils/methyl_utils/core/io.py`](../../packages/methylutils/methyl_utils/core/io.py) (`_row_range_for_bp`, `load_from_h5(..., start_bp=, end_bp=)`, `iter_bp_shards`) and [`MethylFrame.load_from_h5`](../../packages/methylutils/methyl_utils/core/methyl_frame.py); tests in [`test_io.py`](../../packages/methylutils/methyl_utils/tests/test_io.py).

azure_devops:
  type: Feature
  epic: AB#413
  title: MethylSample bp-ranged H5 I/O
  description: "Genomic range load helpers for MethylSample H5 (contiguous row slices); no CpG aggregation."
todos:
  - id: range-resolve
    content: Add _row_range_for_bp in io.py (binary search on sorted pos → contiguous lo:hi)
    status: completed
  - id: load-api
    content: Extend load_from_h5 / MethylFrame.load_from_h5 with start_bp/end_bp → slice hyperslab
    status: completed
  - id: shard-iter
    content: Add iter_bp_shards(path, shard_bp) helper for sequential ranged loads
    status: completed
  - id: tests
    content: Unit tests for range resolve, ranged load parity, empty ranges, and shard iteration
    status: completed
  - id: docs-plans
    content: Promote plan to docs/plans/methylsample-bp-ranged-io.plan.md after approval/build
    status: completed
---

# MethylSample bp-ranged I/O (shard index)

## Decision (locked)

Implement **genomic bp sharding for I/O**, not biological window aggregation.

- Same per-CpG rows (`pos`, `mC`, `uC`, `tnc`)
- Smaller entities = contiguous chromosome segments by base-pair range
- Science subsets (DMPs, gene features) keep using existing `positions=` / `indices=` / masks

## Why this is fast

`pos` is stored sorted ascending. Sites in `[start_bp, end_bp)` are a **contiguous row run**, so load is a hyperslab `dset[lo:hi]` — cheaper than fancy-index reads used for scattered `positions=`.

```mermaid
flowchart LR
  Range["start_bp, end_bp"] --> BinSearch["2x binary search on pos"]
  BinSearch --> Slice["lo:hi contiguous"]
  Slice --> Hyperslab["H5 pos/mC/uC/tnc lo:hi"]
  Hyperslab --> Sample["MethylSample subset"]
```

## Delivered

### [`packages/methylutils/methyl_utils/core/io.py`](../../packages/methylutils/methyl_utils/core/io.py)

1. **`_row_range_for_bp(pos_dset_or_arr, start_bp, end_bp) -> (lo, hi)`** — half-open `[start_bp, end_bp)` via searchsorted (array or H5 dataset).
2. **`load_from_h5(..., start_bp=None, end_bp=None)`** — contiguous slice hyperslab; mutually exclusive with `positions=` / `indices=`.
3. **`iter_bp_shards(path, shard_bp, *, start_bp=None, end_bp=None)`** — successive non-overlapping shards; `shard_bp` caller-provided (no package default).

Wired through [`MethylFrame.load_from_h5`](../../packages/methylutils/methyl_utils/core/methyl_frame.py); exported as `iter_bp_shards` from `methyl_utils`.

### Tests

[`packages/methylutils/methyl_utils/tests/test_io.py`](../../packages/methylutils/methyl_utils/tests/test_io.py) — range resolve, ranged load parity, empty/out-of-range, conflict with `positions=`, shard concatenation.

## Out of scope (explicit)

- No CpG collapse / mean-β window rows inside `MethylSample`
- No schema change requiring rewrite of existing `{chr}-{ctx}.h5` files for v1
- No mandatory coarse on-disk shard index group
- No wholesale rewiring of centroid builder / classifier / derived measures — API first
- Does not affect BAM alignment (still extractor → H5)

## Optional follow-up

- Persist `methylation_data/bp_index` (chunk starts → row offsets) on save if profiling warrants it
- Adopt ranged loads in centroid accumulate / PMD loops for memory-bounded chromosome passes
