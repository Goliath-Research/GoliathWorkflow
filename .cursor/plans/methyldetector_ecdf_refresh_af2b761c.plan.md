---
name: MethylDetector ECDF Refresh
overview: Realign `MethylDetector` around the code’s actual ECDF/effect-coverage pipeline, then improve biological validity and speed by removing unsupported distribution paths, fixing evaluation leakage, and eliminating repeated validation/classifier rebuild work. Keep a second, optional phase for a deeper shift to bin-count-based rank testing and heterogeneity-aware filtering.
todos:
  - id: align-source-of-truth
    content: "Align docs/config/runtime surface around the actual live detector: Welch/FDR -> lazy ECDF rescoring -> per-context effect_size_coverage -> validation BA."
    status: pending
  - id: remove-legacy-distributions
    content: Remove or hard-fail unsupported Beta/Normal/Beta-Binomial runtime branches and fallbacks from config, centroid comparison, classifier/export metadata, and docs.
    status: pending
  - id: fix-validation-rigour
    content: Make top-k selection biologically trustworthy by eliminating evaluation leakage, stopping EAT from editing p/q-values, and requiring held-out or repeated stratified validation for BA reporting.
    status: pending
  - id: cache-and-vectorize-hotpaths
    content: Cache centroid histograms/ECDF classifier inputs across candidate k values, vectorize real-sample extraction/remapping, and avoid repeated full H5 loads during optimization.
    status: pending
  - id: optional-assumption-light-gate
    content: If desired after baseline cleanup, replace the Welch gate with a bin-count-based Mann-Whitney test and add tau2 heterogeneity filtering / biological-only rescue as a second-phase algorithmic upgrade.
    status: pending
  - id: add-regression-tests
    content: Add focused detector tests for ECDF-only enforcement, effect_size_coverage behavior, held-out validation, and any new statistical-gate / heterogeneity logic.
    status: pending
isProject: false
---

# MethylDetector Bio-Soundness And Speed

## Current Truth

- The live detector is centered in [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py) and currently runs: `delta_mean_reduction` pre-gate -> Welch + `fdr_tsbh` -> lazy ECDF overlap/effect-size recomputation -> per-context `effect_size_coverage` selection -> BA-based top-k optimization.
- The code is not fully ECDF-only yet. [packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py), [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py), [packages/methylutils/methyl_utils/beta_classifier.py](packages/methylutils/methyl_utils/beta_classifier.py), and [packages/methylutils/methyl_utils/core/distribution_views.py](packages/methylutils/methyl_utils/core/distribution_views.py) still expose `normal`, `beta`, mixture, or beta-binomial paths, while [packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md](packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md) and [packages/methyldetector/README.md](packages/methyldetector/README.md) already describe a cleaner ECDF-only story.
- The main performance bottlenecks are downstream of detection, not just the statistical gate: [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py) still loads full sample H5s and fills the validation matrix with Python loops, [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py) rebuilds an `ECDFClassifier` and reloads centroid bin counts for many candidate `k` values, and [packages/methylutils/methyl_utils/ecdf_classifier.py](packages/methylutils/methyl_utils/ecdf_classifier.py) still loops per DMP inside `predict_proba()`.
- The current BA optimization is not a clean estimate of generalization when `validation_split_ratio=0`: [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py) uses the same samples for calibration and evaluation, and `featurecuts` chooses `k` on that same cohort. EAT also still edits `p_value` / `q_value`, which mixes biological prior weighting into the statistical gate.

## Target Flow

```mermaid
flowchart LR
    centroids[Centroids_plus_binned_stats] --> statsGate[StatsGate]
    statsGate --> bioSelect[PerContext_effectCoverage]
    bioSelect --> heldOutSelect[HeldOut_topK_selection]
    heldOutSelect --> ecdfModel[ECDF_only_classifier_and_export]
```



## Proposed Work

- Make [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py) and [packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py) the source of truth, then update [packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md](packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md), [packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md](packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md), and [packages/methyldetector/README.md](packages/methyldetector/README.md) so the documented algorithm matches the live one.
- Do a high-confidence cleanup first: remove stale `distribution`, `delta_mean_mode`, `overlap_mode`, `Beta-Binomial`, and `BetaClassifier` fallback surface from [packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py), [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py), [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py), and export metadata. The existing internal design notes in [.cursor/plans/ecdf-only_centroid_comparison_5b06ca4b.plan.md](.cursor/plans/ecdf-only_centroid_comparison_5b06ca4b.plan.md) and [.cursor/plans/ecdfclassifier_replacing_betaclassifier_872ba2de.plan.md](.cursor/plans/ecdfclassifier_replacing_betaclassifier_872ba2de.plan.md) are a good baseline for this pass.
- Improve biological trustworthiness before changing the core test: keep `effect_size_coverage` as the main per-context selector, stop EAT from modifying p/q-values, and make BA selection/reporting use held-out or repeated stratified validation instead of the same cohort used to choose `k`. The current project config in [configs/project_Healthy_vs_PCa1-4.json](configs/project_Healthy_vs_PCa1-4.json) should become the acceptance config for this behavior.
- Attack the real hot spots: cache per-(chromosome, context) centroid `bin_counts` and any derived ECDF tables once, replace repeated `_extract_bin_counts_for_dmps()` / `ECDFClassifier.from_dataframe()` rebuilds with prefix-aware scoring for top-k subsets, and vectorize or position-restrict the validation extraction path in [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py) and [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py).
- After the baseline cleanup, optionally implement the deeper “assumption-light” redesign from [.cursor/plans/assumption-free_funnel_ba63abc2.plan.md](.cursor/plans/assumption-free_funnel_ba63abc2.plan.md): replace the Welch gate with a vectorized Mann-Whitney test from `bin_counts`, add `tau2` heterogeneity columns from existing centroid fields, and keep biologically strong but underpowered loci separate via explicit flags instead of silently mixing them into the confirmed statistical DMP set.

## Key Files

- [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)
- [packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py)
- [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)
- [packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py)
- [packages/methylutils/methyl_utils/ecdf_classifier.py](packages/methylutils/methyl_utils/ecdf_classifier.py)
- [packages/methylutils/methyl_utils/core/distribution_views.py](packages/methylutils/methyl_utils/core/distribution_views.py)
- [packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md](packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md)
- [packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md](packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md)
- [packages/methyldetector/README.md](packages/methyldetector/README.md)
- [configs/project_Healthy_vs_PCa1-4.json](configs/project_Healthy_vs_PCa1-4.json)

## Success Criteria

- One documented detector story: no more docs claiming ECDF-only while runtime still uses Beta/Normal/Beta-Binomial branches.
- Optimization no longer rebuilds the classifier and reloads centroid histograms for every candidate `k`.
- Reported BA comes from a held-out or repeated validation path rather than the same samples used to choose `k`.
- The detector still favors biologically strong DMPs through per-context `effect_size_coverage`, with a clear path to stricter, assumption-lighter statistics if that second phase is wanted.

