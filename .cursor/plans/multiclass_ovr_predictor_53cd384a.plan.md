---
name: Multiclass OvR predictor
overview: Introduce a versioned PKL and runtime path for K-way OvR over binary ECDFs, with OvR orchestration owned by MethylClassifier (SOLID), union DMP loading, dual tqdm, and existing multiclass metrics in MethylPredictor.
todos:
  - id: bundle-spec
    content: Define ecdf_one_vs_rest PKL schema + union dmp_df construction
    status: pending
  - id: ovr-methylclassifier
    content: Implement OvR multiclass inside MethylClassifier (column maps + K-way predict_proba dispatch)
    status: pending
  - id: load-classifier
    content: Extend MethylClassifier.load_classifier + get_feature_info + predict_proba for OvR mode
    status: pending
  - id: classify-path
    content: Add multiclass OvR branch in classify_samples_from_list + dual tqdm (load + predict)
    status: pending
  - id: predictor-wire
    content: Adjust run_prediction messaging / dmp_positions_df for K>2 OvR
    status: pending
  - id: export-min
    content: Minimal PKL builder from K binary ECDF packages + docs
    status: pending
  - id: tests
    content: Unit tests for MethylClassifier OvR mode + predictor integration with K=3
    status: pending
isProject: false
---

# Multiclass OvR ECDF for MethylPredictor

## Current gaps

- `**[run_prediction](packages/methylpredictor/methyl_predictor/core/predictor.py)**` assumes `MethylClassifier` exposes either a **multi-chromosome binary bundle** (`is_multi_chromosome`) or a **single inner** `predict_proba` with shape `(n_samples, K)`. There is **no** path where `**MethylClassifier` itself** composes **K binary ECDF sub-models** (OvR), merges scores to `P(class 0..K-1)`, and exposes the **same public API** (`predict_proba`, `get_feature_info`, union DMPs) as the binary case.
- `**[classify_samples_from_list](packages/methylclassifier/methyl_classifier/cli/main.py)`** branches on `is_multi_chromosome` vs **single-file multi-chrom** `[_classify_single_file_multichrom_dmps](packages/methylclassifier/methyl_classifier/cli/main.py)` vs single-chrom. For **multiclass on multiple chromosomes** with a **single** `dmp_positions_df`, the multi-chrom path is correct only when `dmp_df["chromosome"].nunique() > 1`. If `n_classes > 2` but the **else** branch runs (e.g. single chrom in `dmp_df` or missing column), **only one chromosome** of loaded data is used — unsafe for full-genome OvR.
- `**[multiclass_builder.py](packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py)`** references `MultiClassClassifier` while importing `MultiClassBetaMixtureClassifier` — the Beta multiclass path is **not aligned** with ECDF-only direction; treat as **legacy / out of scope** unless you explicitly want it repaired in the same effort.

## Target behavior (your spec)

```mermaid
flowchart LR
  loadPkl[Load PKL into MethylClassifier]
  unionDMP[MethylClassifier builds union DMP df]
  loadH5[DataLoader uses union mask once]
  predict[MethylClassifier.predict_proba OvR dispatch]
  metrics[K-way metrics in MethylPredictor]
  loadPkl --> unionDMP --> loadH5 --> predict --> metrics
```



**SOLID placement:** `ECDFClassifier` in methylutils stays a **pure binary** likelihood model. `**MethylClassifier`** is the **facade**: for `K == 2` it behaves as today (single `self.classifier` or multi-chromosome bundle); for `**K > 2`** in OvR mode it **owns** the list of binary ECDFs, column maps, fusion rule, and `dmp_positions_df` union—callers (CLI, MethylPredictor) use `**MethylClassifier` only**, not a separate top-level multiclass type in methylutils.

1. **Load** the multiclass artifact and enumerate **all** binary ECDF sub-models and their per-model DMP lists (chromosome / position / context as needed).
2. **Union** DMPs (per chromosome, merge contexts as today) into the structure `**dmp_positions_by_chrom`** / `dmp_positions_df` already consumed by `[DataLoader.load_samples_from_list](packages/methylclassifier/methyl_classifier/utils/data_loader.py)` so **each sample directory is read once** and **no further HDF5 access** for that phase.
3. **Build** a single feature matrix aligned to a **global column order** (documented: e.g. sorted `(chrom, pos, context)` or `dmp_df` row order), with a **column index map** into each binary model’s expected column order.
4. **Apply** OvR: for each of K binary classifiers, slice `X`/`mask`, call `ECDFClassifier.predict_proba` → score for “positive” class; **combine** K scores into a **K-way** probability vector (e.g. softmax over logits derived from `log p_pos - log p_neg`, or normalized positive scores — **pick one rule**, document in code + `[methylpredictor/docs/IMPLEMENTATION.md](packages/methylpredictor/docs/IMPLEMENTATION.md)`).
5. **MethylPredictor**: when labels exist (`test_group_paths` / `expected_classes`), keep using `[_compute_metrics](packages/methylpredictor/methyl_predictor/core/predictor.py)` (already supports `n_classes > 2`, confusion matrix, macro/weighted F1).

## MethylClassifier vs MethylUtils (placement)

| Layer | Owns |
|--------|------|
| **MethylUtils** | `ECDFClassifier` (binary likelihood only). Optionally **stateless** numpy helpers reused elsewhere (e.g. gather columns, or fuse K matrices of shape `(n, 2)` into `(n, K)` given a documented rule). **No** PKL schema, **no** `dmp_positions_df`, **no** multi-chrom / OvR wiring. |
| **MethylClassifier** | **Orchestration**: parse `ecdf_one_vs_rest` bundles, union DMP table, `_ovr_binary_classifiers`, column maps, `predict_proba` / `get_feature_info` dispatch. Calls utils ECDFs (and any tiny fusion helper) internally. |

CLI and MethylPredictor keep using **`MethylClassifier` only**; utils does not become a second public “multiclass classifier” type.

## Control subgroups and test contract

- **OvR does not erase control subgroups.** It needs **K mutually exclusive labels**. If the task is “each sample is one of several control arms or one of several disease cohorts,” set **K = (#control subgroups + #disease groups)** and give each subgroup its **own class index**. OvR is then “class k vs rest” over that flat set.
- **What actually loses subgroups** is collapsing labels or test metadata: e.g. all controls → one training label, or evaluation that only uses binary `test_control_paths` + `test_disease_paths` with a single “control” bucket when you need per-arm truth.
- **MethylPredictor (labeled, K > 2):** use **`test_group_paths`** — a list of `{label, paths}` — so each subgroup maps to a distinct `expected_class`. This matches [`_build_samples_and_expected`](packages/methylpredictor/methyl_predictor/core/predictor.py) when `is_multiclass` and `test_group_paths` is set. Document in predictor docs that **multiclass validation with control subgroups** requires this shape (not a single merged control list).
- **Training / PKL export:** the saved OvR model must be trained with **the same flat K** (each control arm a class if that is the target). Class names in metadata should align with `test_group_paths` labels for human-readable reports.
- **Hierarchical classification** (e.g. first healthy vs disease, then which control subgroup) is **not** the same as flat OvR; treat as a follow-on design if needed.

## Implementation plan

### 1. Serialized bundle contract (OvR ECDF)

Define a **versioned** pickle dict (or small JSON sidecar) written by the **training/export** step (see below), e.g.:

- `package_version`, `classifier_type: "ecdf_one_vs_rest"`
- `class_names: List[str]` (length K)
- `binary_models: List[dict]` length K, each containing:
  - `ecdf`: `ECDFClassifier` (existing)
  - optional `dmp_df` row slice or explicit `positions`, `chromosome`, `context` arrays matching training order
- `metadata`: `n_classes`, training ids, optional temperature overrides

**Union DMP dataframe** for the loader: build `dmp_positions_df` = unique rows across all sub-models’ DMPs (same semantics as merging detection tables), sorted stably; this becomes what `[MethylClassifier.load_classifier](packages/methylclassifier/methyl_classifier/core/classifier.py)` sets when this type is detected.

### 2. OvR logic inside `MethylClassifier` (not a separate public classifier in methylutils)

- Add **private** state on `MethylClassifier`, e.g. `self._ovr_mode: bool`, `self._ovr_binary_classifiers: List[ECDFClassifier]`, `self._ovr_column_indices: List[np.ndarray]` (each maps union columns → that binary model’s column order), plus `class_names` / `n_classes` already present.
- Implement `**_predict_proba_ovr(X, mask) -> (n_samples, K)`** (and optionally `_build_union_feature_info()`) as **methods on `MethylClassifier`** or a **small private helper class** colocated in `[packages/methylclassifier/methyl_classifier/core/](packages/methylclassifier/methyl_classifier/core/)` (e.g. `multiclass_ovr.py` imported only by `classifier.py`) so the **orchestration** package is methylclassifier, not methylutils.
- `**predict_proba` / `predict`** on `MethylClassifier`: if `self._ovr_mode`, delegate to `_predict_proba_ovr`; elif `is_multi_chromosome`, existing combine path; else delegate to `self.classifier` (binary).
- `**get_feature_info`**: in OvR mode return `**n_features**` = union width and `**positions**` (and chromosome/context metadata) consistent with `dmp_positions_df` row order used by the loader.
- `**load_classifier**`: when `classifier_type == "ecdf_one_vs_rest"`, parse `binary_models`, build union `dmp_positions_df`, set `_ovr_*` fields, set `self.classifier = None` (or keep unused) and `self.is_multi_chromosome = False` unless you later combine OvR with per-chrom bundles (out of scope unless specified).

Optional: **tiny** numpy-only helpers in methylutils (e.g. column gather) if they are reused elsewhere; **no** `ECDFOneVsRestClassifier` as the object stored in `model_package['classifier']`—the PKL remains a **dict** that `MethylClassifier` consumes, matching “MethylClassifier creates / holds multiclass when needed.”

### 3. Classification path in `classify_samples_from_list`

- For `**n_classes > 2`** and `MethylClassifier` in OvR mode (`_ovr_mode`), route to a **dedicated** helper (extend `[_classify_single_file_multichrom_dmps](packages/methylclassifier/methyl_classifier/cli/main.py)` or add `_classify_ovr_ecdf_multiclass`) that:
  1. Uses **union** `dmp_positions_df` for loading (already true if `run_prediction` passes it through).
  2. Fills `feature_matrix` / `availability_mask` **once** over all samples (existing pattern: tqdm **“Loading / extracting features”** — align naming with your UX: first bar = **read from disk** during `[load_samples_from_list](packages/methylclassifier/methyl_classifier/utils/data_loader.py)` which already has tqdm **“Loading samples”**).
  3. Second tqdm: **predict_proba per sample** (row loop) calling `**classifier.predict_proba`** (dispatches to `_predict_proba_ovr` on `MethylClassifier`) — acceptable cost for UX; optional `batch_size` later if needed.

Ensure `**classify_samples_batch**` does not double-call `predict_proba` for multi-chrom binary paths (already fixed elsewhere); OvR path should call `**MethylClassifier.predict_proba` once per row** inside tqdm (or batch if optimized later).

### 4. MethylPredictor

- In `[run_prediction](packages/methylpredictor/methyl_predictor/core/predictor.py)`, after `MethylClassifier` load, if `n_classes > 2` and model is OvR (or always when `dmp_positions_df` is set from union), **do not** rely on the fragile `else` single-chrom branch in `classify_samples_from_list`.
- Print a **clear** one-line summary: number of binary sub-models, **union DMP count**, and that **HDF5 is read only during the sample-loading phase**.

### 5. Export / training (minimal)

The predictor cannot run without a PKL. Add a **minimal** builder (script or function on **MethylClassifier** or `methyl_classifier` package) that:

- Takes K trained binary ECDF packages (existing detector output) + class names
- Builds union `dmp_df` + writes `multiclass-classifier.pkl` with `classifier_type: "ecdf_one_vs_rest"` and `binary_models` — **no separate wrapper class** in the pickle as the serialized `classifier` field; the bundle is loaded by `MethylClassifier.load_classifier` which **constructs** in-memory OvR state (or use a thin `MethylClassifier.save` that embeds the same schema).

If the pipeline already has a step that should emit this file, hook it there (e.g. methylvalidation / detector CLI); otherwise document the **manual** build command in `[methylpredictor/docs/USAGE.md](packages/methylpredictor/docs/USAGE.md)`.

### 6. Tests

- **Unit**: `MethylClassifier` in OvR mode (or `_predict_proba_ovr` with injected toy ECDFs) — **3** binaries, overlapping/disjoint DMP columns — assert union width, `predict_proba` shape `(n, 3)`, rows sum to ~1.
- **Integration**: `run_prediction` with temp PKL loaded by `MethylClassifier`, assert CSV + `validation_metrics.json` for K=3.

## Risks / decisions

- **Score fusion rule** (softmax vs normalized OvR positives) affects calibration; document and keep consistent with training if any temperature scaling is applied per binary model.
- **Per-sample `predict_proba`** is slower than batched ECDF; trade explicitly for the second progress bar; document optional batching later.
- **Legacy** `multiclass-classifier.pkl` from Beta builder: either **reject** with a clear error (“expected ecdf_one_vs_rest”) or detect `metadata.classifier_type` and branch — recommend **explicit type field** to avoid silent wrong metrics.

