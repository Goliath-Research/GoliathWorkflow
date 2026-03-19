---
name: MethylClassifier loading progress
overview: "Add visually rich progress during MethylClassifier sample loading and feature extraction using tqdm (or Rich): progress bar, ETA, and current sample name, with optional fallback when the library is not installed."
todos: []
isProject: false
---

# MethylClassifier: Rich Progress with tqdm (or Rich)

## Current behavior

- **Sample loading**: [packages/methylclassifier/methyl_classifier/utils/data_loader.py](packages/methylclassifier/methyl_classifier/utils/data_loader.py) — `load_samples_from_list()` prints one line per sample; no bar, no ETA.
- **Feature extraction**: [packages/methylclassifier/methyl_classifier/cli/main.py](packages/methylclassifier/methyl_classifier/cli/main.py) — Loops over samples with no progress UI before predictions and metrics export.

## Preferred approach: use a progress library

**tqdm** and **Rich** are already used elsewhere in the repo:

- **methylcentroid** uses **tqdm** with an optional fallback (try/except; no hard dependency): `tqdm(..., desc="Adding samples", unit="sample")` and `progress_bar.set_postfix_str(sample_path.name, refresh=True)` to show the current sample ([methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py) ~1054, 1194).
- **methylvalidation** and **methyldetector** use **Rich** (`Progress`, `BarColumn`, `TimeRemainingColumn`, etc.) for a more polished multi-task UI.

Recommendation: use **tqdm** for a simple, consistent look and minimal code (wrap the loop, set postfix for current sample name; ETA is built-in). If you prefer the same style as methylvalidation, use **Rich** instead.

---

## Option A: tqdm (recommended)

- **Dependency**: Add `tqdm` to [packages/methylclassifier/pyproject.toml](packages/methylclassifier/pyproject.toml) (e.g. `tqdm = ">=4.66.0"`).
- **Loading** ([data_loader.py](packages/methylclassifier/methyl_classifier/utils/data_loader.py)):
  - Wrap the loop over `sample_paths` with `tqdm(sample_paths, desc="Loading samples", unit="sample")`.
  - Each iteration: before loading, call `pbar.set_postfix_str(sample_name, refresh=True)` so the bar shows e.g. `Loading samples: 45%|████▌     | 45/100 [02:30<03:00, sample_name]`. tqdm already shows count, percentage, ETA, and rate.
  - On skip/failure: still call `pbar.update(1)` (or rely on iteration) so the bar advances; optional `pbar.set_postfix_str("failed: " + sample_name)` for visibility.
- **Feature extraction** ([main.py](packages/methylclassifier/methyl_classifier/cli/main.py)):
  - In the single-chrom, multi-chrom, and single-file multichrom loops, wrap the sample iteration in `tqdm(..., desc="Extracting features", unit="sample")` and use `set_postfix_str(sample_name)` so users see which sample is being processed before predictions and metrics.
- **Fallback**: Optional try/import tqdm with a no-op fallback (e.g. wrap in a dummy iterator that just yields items) so the CLI still runs without tqdm, with plain print per sample like today.

---

## Option B: Rich

- **Dependency**: Add `rich` to [packages/methylclassifier/pyproject.toml](packages/methylclassifier/pyproject.toml).
- **Pattern**: Use `Progress` with `TextColumn("[bold blue]{task.description}"), BarColumn(), TaskProgressColumn(), TimeRemainingColumn()` (and optionally `TimeElapsedColumn()`). Create one task per phase (e.g. "Loading samples", "Extracting features"). Each step: `task_id = progress.add_task("Loading samples", total=len(sample_paths))` then in the loop `progress.update(task_id, advance=1, description=f"Loading: {sample_name}")` so the current sample is in the description. Same idea for the feature-extraction phase.
- **Look**: Rich gives a boxed, multi-line progress panel and spinners; more verbose and polished than tqdm’s single line.

---

## Implementation summary (Option A — tqdm)


| File                                                                                                       | Change                                                                                                                                                                                                                                   |
| ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [pyproject.toml](packages/methylclassifier/pyproject.toml)                                                 | Add dependency: `tqdm = ">=4.66.0"` (or keep optional with try/except and no extra dep).                                                                                                                                                 |
| [methyl_classifier/utils/data_loader.py](packages/methylclassifier/methyl_classifier/utils/data_loader.py) | In `load_samples_from_list`: wrap `sample_paths` with `tqdm(..., desc="Loading samples", unit="sample")`; inside loop call `pbar.set_postfix_str(sample_name, refresh=True)` and ensure bar advances on success and on skip/fail.        |
| [methyl_classifier/cli/main.py](packages/methylclassifier/methyl_classifier/cli/main.py)                   | In the three feature-extraction loops (single-chrom, multi-chrom, single-file multichrom), wrap iteration in `tqdm(..., desc="Extracting features", unit="sample")` and `set_postfix_str(sample_name)` so the current sample is visible. |


If you choose **Rich** instead, the same two phases (loading + feature extraction) get a `Progress` context and tasks updated with the current sample name; dependency and call sites in data_loader and main.py are the only differences.

## Testing

- Run the classifier on 5–10 samples: confirm a progress bar during load and during feature extraction, with ETA and current sample name updating.
- With tqdm optional: run without tqdm installed and confirm fallback (plain prints or no bar) works.

