---
name: MethylClassifier sample loading
overview: MethylClassifier (and MethylDetector validation) are slow because the shared H5 loader reads the entire `pos` array from every file to find row indices for a few thousand positions. The fix is to compute indices via binary search in the HDF5 dataset so only O(k log n) reads are done instead of loading n positions.
todos: []
isProject: false
---

# MethylClassifier sample loading optimization

## Current behavior

- **MethylClassifier** already passes DMP positions into the loader: `[load_sample_from_directory](packages/methylclassifier/methyl_classifier/utils/data_loader.py)` receives `dmp_positions_by_chrom` and calls `MethylSample.load_from_h5(context_files['CG'], chrom_positions)` per chromosome/context (lines 239, 270). So the “only a few thousand positions” path is in use.
- **MethylDetector** uses the same underlying loader in `[MethylCentroidPair.extract_methylation_fractions](packages/methylutils/methyl_utils/methyl_centroid_pair.py)`: `load_from_h5(h5_file, positions=ctx_positions)` (line 429).
- **Bottleneck** is in `[methyl_utils/core/io.py](packages/methylutils/methyl_utils/core/io.py)` `load_from_h5(..., positions=...)`: for both “methylation_data” Group and root-level formats it does:
  - `pos_arr = np.asarray(methyl_data["pos"][:], dtype=np.uint32)` — **loads the full position array** (e.g. tens of millions of uint32 = hundreds of MB per file),
  - then `idx = _indices_for_positions(pos_arr, positions)` to get row indices,
  - then reads only `pos[idx]`, `mC[idx]`, `uC[idx]`, `tnc[idx]`.

So I/O is dominated by reading the full `pos` dataset once per file; the actual data for the requested positions is a small fraction. With many chromosomes × contexts × samples, this adds up to very long load times.

## Proposed change: index via binary search in H5 (no full-pos read)

- **Assumption**: `pos` in the H5 file is sorted (genomic order), which is the normal layout.
- **Idea**: Do not load the full `pos` array. For each requested position, binary-search in the HDF5 `pos` dataset (single-element or small-slice reads) to get the row index. Total reads: O(k × log(n)) with k = requested positions, n = file length (e.g. k ≈ 5e3, n ≈ 5e7 → ~130k small reads vs one 200MB full read).
- **Placement**: Implement in MethylUtils (shared by MethylClassifier and MethylDetector).

### 1. New helper in [packages/methylutils/methyl_utils/core/io.py](packages/methylutils/methyl_utils/core/io.py)

- Add `_indices_for_positions_h5(pos_dset, positions)` that:
  - Takes an h5py Dataset `pos_dset` (the “pos” array in the file) and a 1D array of requested `positions`.
  - Uses `n = pos_dset.shape[0]` (metadata only).
  - For each value in `positions`, binary-search in `pos_dset` (e.g. read `pos_dset[mid]` at each step) to find the row index; if found, record it (avoid duplicates and keep result in file order: collect (index,) then sort and deduplicate).
  - Returns an integer array of row indices (same semantics as current `_indices_for_positions`: indices into the file where `pos` is in the requested set).
- Keep behavior consistent with current code: only indices where the position exists; if a requested position is missing, it is simply not in the returned index list (downstream already handles missing positions via masks/NaNs).

### 2. Use the helper in `load_from_h5`

- In **Group format** (methylation_data as Group):
  - **Sample** (lines 127–135): replace “load full `pos` then `_indices_for_positions`” with `idx = _indices_for_positions_h5(methyl_data["pos"], positions)` (no `pos_arr = methyl_data["pos"][:]`).
  - **Centroid** (lines 81–84): same replacement when `positions is not None` (use `methyl_data["pos"]` for the binary search, then slice all Group datasets by `idx`).
- In **root-level format** (lines 164–167): replace full `pos` load + `_indices_for_positions` with `idx = _indices_for_positions_h5(f["pos"], positions)`.
- **Structured-array fallback** (single “methylation_data” Dataset, lines 198–206): that path currently does `struct_data = methyl_data[:]` (full load). Leave this path as-is for this change (no separate `pos` dataset to binary-search); optional future work could add a chunked or index-based path for that format.

### 3. No MethylClassifier API changes

- MethylClassifier already passes `dmp_positions_by_chrom` from the classifier’s DMP positions into `DataLoader.load_sample_from_directory` / `load_samples_from_list`. No changes needed there; the speedup comes entirely from the shared loader in MethylUtils.

### 4. Testing

- **Unit test** in MethylUtils for `_indices_for_positions_h5`: e.g. create a small H5 with a sorted `pos` and a “methylation_data” Group, call the helper with a subset of positions (and one missing), assert returned indices match `_indices_for_positions(loaded_pos, positions)`.
- **Regression**: run existing MethylUtils I/O tests and, if available, a quick MethylClassifier run on a small cohort to ensure results and feature vectors are unchanged (only load time should improve).

## Summary


| Component        | Change                                                                                                                                                                |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MethylUtils io   | Add `_indices_for_positions_h5(pos_dset, positions)`; use it in `load_from_h5` for Group and root formats when `positions is not None` instead of loading full `pos`. |
| MethylClassifier | None (already uses position-subset path).                                                                                                                             |
| MethylDetector   | None (benefits via shared loader).                                                                                                                                    |


This keeps a single, consistent loading strategy and improves both MethylClassifier sample loading and MethylDetector validation loading when only a subset of positions is needed.