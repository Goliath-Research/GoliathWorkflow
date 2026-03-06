---
name: Binned stats schema simplification
overview: "Store binned stats only in methylation_data: bins (attr) + bin_counts as a column-like dataset alongside N, Sx, Sx2. No binned_stats group; no bin_edges. Edges derived as np.linspace(0,1,bins+1). No legacy support — rebuild existing centroids."
todos: []
isProject: false
---

# Binned stats: methylation_data only, bin_counts like N/Sx/Sx2

## Goal

- Use **only** the `methylation_data` group. No `binned_stats` group.
- Store **bins** (attribute on `methylation_data` or scalar dataset) and **bin_counts** as a dataset in `methylation_data`, same as N, Sx, Sx2 — so loading by `positions` or `indices` automatically slices `bin_counts` with the same index as the other columns.
- **No legacy support**: Remove all code that reads `binned_stats` or `bin_edges` from H5. Rebuild existing centroids with the new pipeline.
- **Basic MethylSample**: no N, Sx, Sx2, no `bins`, no `bin_counts` — just pos, mC, uC, tnc.

## H5 layout (methylation_data only)

- **Core**: `pos`, `mC`, `uC`, `tnc` (always).
- **Centroid**: `N`, `Sx`, `Sx2` (when centroid).
- **Binned stats** (when centroid has bins): `methylation_data.attrs["bins"]` (int) and dataset `methylation_data["bin_counts"]` with shape `(n_rows, bins)`. Same row order as pos/N/Sx/Sx2 — so when loading with `indices` or `positions`, read `bin_counts[idx]` the same way as `N[idx]`, etc.

Edges are always derived: `bin_edges = np.linspace(0, 1, bins + 1)`.

## Design

1. **Save**: In `save_to_h5`, after writing N, Sx, Sx2, if binned stats exist write `group.attrs["bins"] = n_bins` and `group.create_dataset("bin_counts", data=bin_counts, ...)` in the same `methylation_data` group. Do not create `binned_stats` or write `bin_edges`.
2. **Load**: In `load_from_h5`, when building `data` from `methylation_data`, if `"bins"` in attrs (or present as dataset) and `"bin_counts"` in datasets, load `bin_counts` with the same `idx`/subset as pos, N, Sx, Sx2. Then derive `bin_edges = np.linspace(0, 1, bins + 1)` and call `obj.set_binned_stats(bin_edges, bin_counts)`. Remove any path that reads `binned_stats` or `bin_edges` from the file.
3. **In-memory**: Unchanged: `_binned_stats = {"bin_edges", "bin_counts"}`; `bin_edges` is derived on load from `bins`. Downstream (ECDFView, explorer, MethylCentroidPair) still see `binned_stats` with both keys.

## Files to change

### 1. [packages/methylutils/methyl_utils/core/methyl_frame.py](packages/methylutils/methyl_utils/core/methyl_frame.py)

- **save_to_h5**: Write only inside `methylation_data`. After writing N, Sx, Sx2, if `_binned_stats` and `"bin_counts"` in it: set `group.attrs["bins"] = int(len(bin_edges)-1)` and `group.create_dataset("bin_counts", data=bin_counts, ...)`. No `binned_stats` group, no `bin_edges`.

### 2. [packages/methylutils/methyl_utils/core/io.py](packages/methylutils/methyl_utils/core/io.py)

- **load_from_h5**: When filling `data` from `methylation_data`, treat `bin_counts` like N/Sx/Sx2:
  - If `"bins"` in group.attrs (or as dataset) and `"bin_counts"` in datasets, read `bin_counts` with the same `idx` used for pos/N/Sx/Sx2 (so one consistent slice).
  - After building `obj`, if we loaded `bins` and `bin_counts`, set `bin_edges = np.linspace(0, 1, bins + 1)` and `obj.set_binned_stats(bin_edges, bin_counts)`.
  - **Remove** all logic that checks for or reads `binned_stats` group or `bin_edges` from the file.

### 3. [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)

- **Direct H5 read** (BMM path, ~1688–1720): Read only from `methylation_data`: `bins` from `methylation_data.attrs["bins"]`, `bin_counts` from `methylation_data["bin_counts"]`. Derive `bin_edges = np.linspace(0, 1, bins + 1)` for alignment (same `bins` across centroids) and for any downstream use. **Remove** reads from `binned_stats` or `bin_edges` in the file.

### 4. [packages/methylutils/methyl_utils/core/centroid_builder.py](packages/methylutils/methyl_utils/core/centroid_builder.py)

- No change: still builds centroid in memory with `set_binned_stats(bin_edges, bin_counts)`. Save goes through methyl_frame and writes only bins + bin_counts in methylation_data.

### 5. [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)

- No change to in-memory combine or save_centroid; save_to_h5 handles the new schema.

### 6. Consumers (distribution_views, explorer)

- No API change; they keep using `centroid.binned_stats["bin_edges"]` and `["bin_counts"]` populated in memory from load.

### 7. Tests and docs

- Tests: expect only `methylation_data` (with optional `bins` attr and `bin_counts` dataset); no `binned_stats` group. Remove tests that depend on legacy H5 layout.
- Docs: document that centroid H5 has only `methylation_data`; binned stats are `methylation_data.attrs["bins"]` and `methylation_data["bin_counts"]`; basic sample has no bins/bin_counts.

## Edge cases

- **bins == 0 or missing**: Do not write `bin_counts`; on load do not set binned_stats.
- **Subset load (positions/indices)**: `bin_counts` is loaded with the same index slice as N, Sx, Sx2 (single code path in load_from_h5).

## Summary


| Area                  | Action                                                                                                      |
| --------------------- | ----------------------------------------------------------------------------------------------------------- |
| H5 write              | Only `methylation_data`: bins attr + bin_counts dataset; no other group.                                    |
| H5 read               | Only read from `methylation_data`; bin_counts same slice as N/Sx/Sx2; derive edges. No legacy binned_stats. |
| MethylCentroidPair H5 | Read bins + bin_counts from `methylation_data` only; derive edges.                                          |
| Legacy                | None; remove old binned_stats/bin_edges read paths; rebuild centroids.                                      |


