---
name: Fix MethylCentroid GPU memory leak
overview: "Fix GPU and CPU memory leaks in MethylCentroid by ensuring every GPU/resource-acquiring path explicitly releases resources: close loaded samples in the chunked position loop, run GPU cleanup after each chunk, and tighten builder release in the parallel sample path."
todos: []
isProject: false
---

# Fix MethylCentroid GPU memory leak

## Summary

MethylCentroid uses MethylUtils’ `MemoryManager`, `cleanup_gpu_memory`, and `MethylCentroidBuilder.release_gpu()` for GPU discipline. After recent changes, several paths no longer release resources consistently, leading to memory growth and OOM kills. The fixes below restore explicit acquire/release pairing and add defensive cleanup.

## Root causes

1. **Chunked centroid path**  
   In `_compute_centroid_for_positions`, each sample is loaded via `load_from_h5(..., indices=idx)` or `load_sample()` into `sample_data_obj`, but **`sample_data_obj` is never closed**. References (and any GPU/MMAP resources) are only dropped when the variable is overwritten or when the function returns, which can accumulate across many samples and chunks.

2. **Cleanup only at end of chunked run**  
   In `compute_centroid_chunked`, `memory_manager.force_gpu_cleanup()` is called only **once** after all chunks (around line 1790). Any GPU use inside `_compute_centroid_for_positions` (e.g. from `_ensure_numpy_arrays`/`to_cpu()` or from load paths) can therefore accumulate across chunks and never be released until the full run finishes.

3. **Builder in parallel path (defense in depth)**  
   In the parallel sample-addition path, when the first sample is processed we create a `MethylCentroidBuilder`, then call `builder.finalize(log_finalize=False)`, which already calls `release_gpu()`. The `finally` block only does `del builder`. Explicitly calling `builder.release_gpu()` before `del builder` when `builder is not None` makes the release contract clear and robust to future changes in `finalize()`.

## Implementation plan

### 1. Close loaded samples in `_compute_centroid_for_positions` (MethylCentroid)

**File:** [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)

In the per-sample loop (over `sample_idx`), wrap the use of `sample_data_obj` in a `try`/`finally` and in the `finally` block:

- If `sample_data_obj` is not None and has a `close` method, call `sample_data_obj.close()` (and optionally `sample_data_obj = None`).
- Catch and log any exception from `close()` so a single failure does not break the loop.

This ensures every loaded sample (from either `load_from_h5(..., indices=idx)` or `load_sample()`) is explicitly released after use, freeing references and any GPU/MMAP resources as soon as each sample is processed.

### 2. Run GPU cleanup after each chunk in `compute_centroid_chunked` (MethylCentroid)

**File:** [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)

Inside the `for chunk_idx in tqdm(...)` loop, **after** processing the chunk (after the `_compute_centroid_for_positions` call and appending to `chunk_results` / `chunk_bin_counts`), call:

- `memory_manager.force_gpu_cleanup()`

so that GPU memory used during that chunk (including any temporaries from loading/aligning samples) is released before the next chunk. Keep the existing `force_gpu_cleanup()` at the end of `compute_centroid_chunked` as well for a final cleanup.

### 3. Explicitly release builder GPU in parallel path (MethylCentroid)

**File:** [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)

In the `finally` block of the parallel sample-addition loop (where we currently have `if builder is not None: del builder`), **before** `del builder`:

- If `builder is not None`, call `builder.release_gpu()` in a try/except (log and ignore exceptions) so that GPU arrays are released even if `finalize()` behavior changes later. Then perform `del builder` as now.

### 4. Optional: per-chunk CPU relief for `pos_cache` (if needed later)

**File:** [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)

`pos_cache` in `compute_centroid_chunked` holds one full `pos` array per sample for the entire chunked run. For many samples and large chromosomes this can use a lot of RAM. The current design avoids re-reading each file’s `pos` on every chunk. If memory pressure remains after the above fixes, consider (in a follow-up):

- Adding a config or environment flag to disable `pos_cache` (or to clear it after each chunk and re-read `pos` per chunk), trading some I/O for lower peak RAM; or
- Capping the number of samples whose `pos` is cached and evicting oldest entries.

Do **not** change `pos_cache` behavior in the initial leak fix; only document it as a possible future tuning point if OOM persists.

## Verification

- Re-run the same pipeline that was previously killed by memory pressure (e.g. `methyl-centroid --project configs/project_Healthy_vs_PCa1-4.json --group all`).
- Monitor GPU memory (e.g. `nvidia-smi`) and process RSS across multiple (chrom, context) combinations; both should stabilize or drop between combinations and not grow unbounded within a single centroid build.
- Run existing MethylCentroid tests to ensure no regressions.

## Files to touch

| File | Change |
|------|--------|
| [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py) | (1) Close `sample_data_obj` in `_compute_centroid_for_positions` per-sample loop; (2) Call `memory_manager.force_gpu_cleanup()` after each chunk in `compute_centroid_chunked`; (3) Call `builder.release_gpu()` before `del builder` in the parallel path `finally` block. |

No changes to MethylUtils are required for this plan; the leak is in MethylCentroid’s use of loaded samples and timing of cleanup. MethylUtils’ `MemoryManager.force_gpu_cleanup()` and `MethylCentroidBuilder.release_gpu()` are already used; this plan ensures they are called at the right points.
