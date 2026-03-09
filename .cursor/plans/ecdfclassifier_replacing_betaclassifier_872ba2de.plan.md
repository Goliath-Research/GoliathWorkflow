---
name: ECDFClassifier replacing BetaClassifier
overview: Design and implement an ECDFClassifier that replaces BetaClassifier. The weighted log-likelihood formula and the prediction pipeline are unchanged; only the per-position density model changes from Beta(alpha, beta) to the PCHIP-derived PDF from the centroid's binned_stats.
todos:
  - id: ecdf-classifier-class
    content: Create ECDFClassifier class in methyl_utils/ecdf_classifier.py with predict_proba, from_dataframe, save, and load methods.
    status: pending
  - id: ecdf-classifier-bin-extract
    content: Add _extract_bin_counts_for_dmps helper to MethylDetector that loads bin_counts from centroid H5 at selected DMP positions.
    status: pending
  - id: ecdf-classifier-replace-beta
    content: Replace all three BetaClassifier.from_dataframe call sites in methyldetector.py with ECDFClassifier.from_dataframe.
    status: pending
  - id: ecdf-classifier-export
    content: Export ECDFClassifier from methyl_utils/__init__.py.
    status: pending
isProject: false
---

# ECDFClassifier: replacing BetaClassifier

## Why the change is straightforward

BetaClassifier and ECDFClassifier share the same formula:

```
log L(class_k | x) = Σ_i  w_i · log p_k_i(x_i)

P(class_k | x) ∝ exp( log L / T )
```

The only difference is what `p_k_i(x_i)` is:


|                               | BetaClassifier           | ECDFClassifier               |
| ----------------------------- | ------------------------ | ---------------------------- |
| Density                       | `Beta(x; α_k_i, β_k_i)`  | `F'_k_i(x)` via PCHIP spline |
| Parameters stored per DMP     | `alpha_k_i, beta_k_i`    | `bin_counts_k_i[n_bins]`     |
| Handles bimodal distributions | No — unimodal assumption | Yes                          |
| Consistent with DMP detection | No (different model)     | Yes                          |


Everything else — input format (fraction matrix), NaN masking, effect_size weights, temperature scaling, prior odds — is unchanged.

---

## Data available for the ECDF classifier

For each selected DMP position `i` and each centroid (class), the detector already has:

- `bin_edges` (shared, shape `(n_bins+1,)` = 21 for default 20 bins)
- `bin_counts_k[i]` (shape `(n_bins,)`) from `centroid.binned_stats["bin_counts"][idx_i]`

These are exactly what `ECDFView.__init_`_ uses to build one `PchipInterpolator` per position.

The lazy ECDFView construction already implemented in `_detect_statistical_dmps_for_context` (line ~449) does this index lookup:

```python
idx_in_c1 = np.searchsorted(pos1, dmp_positions)
idx_in_c2 = np.searchsorted(pos2, dmp_positions)
bin_counts_c1 = bs1["bin_counts"][idx_in_c1]   # shape (n_dmps, n_bins)
bin_counts_c2 = bs2["bin_counts"][idx_in_c2]   # shape (n_dmps, n_bins)
```

The problem is that by the time the classifier is built, the centroid objects are no longer in scope — the pipeline works on the concatenated DMP DataFrame from all chromosomes/contexts. So the `bin_counts` must either be:

**Option A** — Stored in the DMP DataFrame as columns at detection time, or  
**Option B** — Re-loaded from the centroid H5 files at classifier-building time (using `centroid1_dir`/`centroid2_dir` + chromosome + context)

Option B keeps the DMP DataFrame lightweight and is cleaner. The centroid H5 files are always available at classifier-build time because the detector already uses them.

---

## New class: `ECDFClassifier`

**Location:** new file `packages/methylutils/methyl_utils/ecdf_classifier.py`

```python
class ECDFClassifier:
    """
    Per-position ECDF log-likelihood classifier.

    log L(class_k | x) = Σ_i  w_i · log F'_k_i(x_i)
    P(class_k | x) ∝ exp(log L(class_k | x) / T)

    Identical structure to BetaClassifier; only the density model changes.
    """

    def __init__(
        self,
        positions: np.ndarray,        # (n_dmps,) uint32
        bin_edges: np.ndarray,         # (n_bins+1,) shared
        bin_counts_c1: np.ndarray,     # (n_dmps, n_bins) class 0
        bin_counts_c2: np.ndarray,     # (n_dmps, n_bins) class 1
        weights: np.ndarray,           # (n_dmps,) effect_size, normalized to [1e-6, 1]
        directions: np.ndarray,        # (n_dmps,) int8: +1 hyper, -1 hypo
        temperature: float = 2.0,
        n_classes: int = 2,
    ):
        ...
        # Build ECDFViews for each class (lazy: only DMP positions, not full centroid)
        self._view_c1 = ECDFView(bin_edges, bin_counts_c1, Sx1, N1, Sx2_1)
        self._view_c2 = ECDFView(bin_edges, bin_counts_c2, Sx2, N2, Sx2_2)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        X: shape (n_samples, n_dmps), float in [0,1], NaN for missing positions.
        Returns: (n_samples, 2) posterior probabilities.
        """
        n_samples, n_pos = X.shape
        availability = np.isfinite(X)              # (n_samples, n_pos)
        X_clean = np.where(availability, X, 0.5)   # NaN → 0.5 (neutral)
        X_clean = np.clip(X_clean, 1e-7, 1 - 1e-7)

        # Evaluate PDF for all positions at once using _pdf_batch
        # _pdf_batch returns shape (n_pos, grid_size) — need point evaluation
        log_p_c1 = np.zeros((n_samples, n_pos))
        log_p_c2 = np.zeros((n_samples, n_pos))
        for i in range(n_pos):
            for s in range(n_samples):
                if availability[s, i]:
                    log_p_c1[s, i] = np.log(max(self._view_c1._pdf(i, X_clean[s, i]), 1e-300))
                    log_p_c2[s, i] = np.log(max(self._view_c2._pdf(i, X_clean[s, i]), 1e-300))

        # Weighted sum
        log_like_c1 = np.sum(self.weights[np.newaxis, :] * log_p_c1, axis=1)
        log_like_c2 = np.sum(self.weights[np.newaxis, :] * log_p_c2, axis=1)

        # Temperature-scaled softmax (identical to BetaClassifier)
        log_likes = np.stack([log_like_c1, log_like_c2], axis=1) / self.temperature
        log_likes -= log_likes.max(axis=1, keepdims=True)
        probs = np.exp(log_likes)
        return probs / probs.sum(axis=1, keepdims=True)
```

**Performance note:** The per-sample, per-position Python loop above is the simplest implementation. For the number of selected DMPs (typically 100–10,000) and validation samples (typically 20–200), it is fast enough. A vectorized version using `_pdf_batch` on a per-sample grid would require evaluating at arbitrary `x` values across samples, not a fixed grid — this can be optimized later using `np.interp` against a pre-computed dense PDF table.

---

## Changes to the pipeline

### 1. New helper in `methyldetector.py`: `_extract_bin_counts_for_dmps`

```python
def _extract_bin_counts_for_dmps(
    self,
    dmp_positions: np.ndarray,   # sorted uint32 positions
    context: str,
    chromosome: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Load centroid H5 files for chromosome/context and extract bin_counts
    at the given DMP positions.  Returns (bin_edges, bc1, bc2).
    """
    c1_path = Path(self.config.centroid1_dir) / f"{chromosome}-{context}.h5"
    c2_path = Path(self.config.centroid2_dir) / f"{chromosome}-{context}.h5"
    c1 = load_from_h5(c1_path)
    c2 = load_from_h5(c2_path)
    bin_edges = np.asarray(c1.binned_stats["bin_edges"], dtype=np.float64)
    idx1 = np.searchsorted(c1.pos.values, dmp_positions)
    idx2 = np.searchsorted(c2.pos.values, dmp_positions)
    bc1 = np.asarray(c1.binned_stats["bin_counts"], dtype=np.float64)[idx1]
    bc2 = np.asarray(c2.binned_stats["bin_counts"], dtype=np.float64)[idx2]
    return bin_edges, bc1, bc2
```

### 2. Replace `BetaClassifier.from_dataframe` call

Currently in `methyldetector.py` (around line 1461):

```python
# Before:
classifier = BetaClassifier.from_dataframe(dmpDF, ...)

# After:
bin_edges, bc1, bc2 = self._extract_bin_counts_for_dmps(
    dmp_positions, context=ctx, chromosome=chrom
)
classifier = ECDFClassifier.from_dataframe(dmpDF, bin_edges, bc1, bc2, temperature=...)
```

The `dmpDF` still carries `pos`, `weight` (effect_size), `delta_sign`. The `alpha1/beta1/alpha2/beta2` columns are no longer needed for the classifier itself but can stay in the DMP CSV output for reference.

### 3. Model serialization

Add `save` / `load` to `ECDFClassifier`:

```python
def save(self, path: str):
    np.savez_compressed(path,
        positions=self.positions,
        bin_edges=self.bin_edges,
        bin_counts_c1=self.bin_counts_c1,
        bin_counts_c2=self.bin_counts_c2,
        weights=self.weights,
        directions=self.directions,
        temperature=np.array([self.temperature]),
    )

@classmethod
def load(cls, path: str) -> "ECDFClassifier":
    d = np.load(path)
    return cls(d["positions"], d["bin_edges"], d["bin_counts_c1"], d["bin_counts_c2"],
               d["weights"], d["directions"], float(d["temperature"]))
```

### 4. `alpha1/beta1/alpha2/beta2` in `CENTROID_COMPARISON_DTYPE`

Can be removed once `ECDFClassifier` is fully in place. The EAT transformation also consumes them, so they should stay until EAT is either ported to an ECDF-based formulation or removed. This is a separate follow-on step.

---

## Summary of files changed


| File                                                             | Change                                                                                                                           |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `packages/methylutils/methyl_utils/ecdf_classifier.py`           | New file: ECDFClassifier class                                                                                                   |
| `packages/methylutils/methyl_utils/__init__.py`                  | Export ECDFClassifier                                                                                                            |
| `packages/methyldetector/methyl_detector/core/methyldetector.py` | Add `_extract_bin_counts_for_dmps`; replace `BetaClassifier.from_dataframe` calls (3 sites) with `ECDFClassifier.from_dataframe` |
| `packages/methyldetector/methyl_detector/core/methyldetector.py` | Update model save/load paths to use `.npz` instead of whatever format BetaClassifier uses                                        |


