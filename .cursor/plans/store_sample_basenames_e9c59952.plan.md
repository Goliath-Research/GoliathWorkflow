---
name: Store sample basenames
overview: Fix `_get_active_sample_paths()` in the MethylCentroid runner to store sample basenames (e.g. `SAMPLE001`) instead of full directory paths (e.g. `/data/samples/SAMPLE001`) in the centroid's H5 metadata under `samples_used`.
todos:
  - id: fix-active-sample-paths
    content: Change both branches in _get_active_sample_paths() (methyl_centroid.py lines 650-664) from str(sample_path.parent) to sample_path.parent.name
    status: pending
isProject: false
---

# Store Sample Basenames in MethylCentroid

## Problem

`[_get_active_sample_paths()](packages/methylcentroid/methyl_centroid/methyl_centroid.py)` returns `str(sample_path.parent)` (full path) in both branches:

```python
# Both branches currently do this:
active_paths.append(
    str(sample_path.parent)        # e.g. "/data/samples/SAMPLE001"
    if hasattr(sample_path, "parent")
    else str(Path(sample_path).parent)
)
```

These full paths are stored as `metadata["samples_used"]` in the saved H5 file (line 1411). Only the basename is needed.

## Fix

In `[packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)`, change both branches of `_get_active_sample_paths()` (lines 648–664) to use `.parent.name` (basename):

```python
active_paths.append(
    sample_path.parent.name
    if hasattr(sample_path, "parent")
    else Path(sample_path).parent.name
)
```

Apply this change to both the `is_new_sample` branch (lines 650–654) and the `else` branch (lines 660–664).

## Deduplication guarantee

- `self.samples` and `self.add_samples` are both deduplicated at construction time by `p.parent.name` (lines 208–221 and `_deduplicate_add_samples()`), so `active_samples` already contains no duplicate basenames.
- No additional deduplication is needed in `_get_active_sample_paths()` itself.

## Scope

Only `_get_active_sample_paths()` needs to change. The `samples` property on `MethylCentroidData` (`methyl_frame.py` line 332) reads back whatever is stored under `samples_used` — it requires no changes.