---
name: ECDF-only cleanup and docs
overview: Clean break to an ECDF-only MethylDetector. Remove EAT, alpha/beta export, and all Beta/Normal/Beta-Binomial/BetaMixture references. Removed features are not exported and not mentioned in documentation. No backward compatibility. Simplify JSON config files by dropping obsolete options.
todos: []
isProject: false
---

# MethylDetector ECDF-only cleanup and documentation update

## Principles

- **Clean new version**: No backward compatibility. Removed features are not exported and are not mentioned anywhere in documentation (no "deprecated" or "legacy" sections).
- **Documentation**: Only describe what exists. Delete every mention of EAT, BMM, alpha/beta in export, classifier_type alternatives, and parametric distributions; do not retain "for reference" or deprecation notes.
- **Config**: Simplify JSON configs so they only include options the detector actually uses; remove obsolete keys.

## Scope

- **In scope**: MethylDetector package only. Remove EAT, alpha/beta from export, and all code/docs referencing Beta/Normal/Beta-Binomial/BetaMixture. Simplify detection config in JSON files.
- **Out of scope**: MethylUtils (may still expose Beta/EAT for other pipelines; MethylDetector simply does not use them).

---

## 1. Remove EAT and Beta-parameter dependency (code and config)

### 1.1 Config ([packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py))

- **Remove entire EAT section**: delete `enable_eat_transform`, `eat_gamma`, `eat_clip_t`, `eat_normalization`, `eat_low_tau_threshold`.
- **Remove** the `eat_normalization` field validator.
- **classifier_type**: Keep validation to `"ecdf"` only; keep or shorten description (no mention of "legacy" alternatives).

### 1.2 Core ([packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py))

- **Remove EAT import and guard**: delete the block that imports `compute_eat_T` and sets `EAT_AVAILABLE`.
- **Remove EAT application block**: delete the `if self.config.enable_eat_transform` block and the call to `_apply_eat_transformation`.
- **Remove `_apply_eat_transformation`**: delete the entire method (uses alpha1, beta1, alpha2, beta2 and compute_eat_T).
- **Remove eat_effect_weight from effect_size path**: delete the branch that multiplies `effect_size` by `eat_effect_weight` (so effect_size is never EAT-modified).
- **Remove alpha/beta from export**: remove `alpha1`, `beta1`, `alpha2`, `beta2` from `EXTRA_EXPORT_COLS` (or equivalent export column list) and from the dtype map used for export/model package.
- **Mock validation data**: replace `np.random.beta(3,1,...)` and `np.random.beta(1,3,...)` with e.g. `np.random.uniform(0.2, 0.8, ...)` and `np.random.uniform(0.5, 1.0, ...)` so the detector code does not reference Beta.
- **Keep** `DIST_NAMES = {5: 'ECDF'}` and dist/dist_name logic unchanged.

### 1.3 Legacy validator ([packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py))

- **Keep** rejection of `distribution`, `delta_mean_mode`, `overlap_mode`, `max_N_for_ecdf`, `statistical_test` so invalid keys are rejected at load time. Do not document these keys anywhere.

---

## 2. Documentation updates (clean removal only)

Removed features are not mentioned. Do not add "deprecated" or "formerly" sections.

### 2.1 HTML docs

- **[packages/methyldetector/docs/MethylDetector_Theory.html](packages/methyldetector/docs/MethylDetector_Theory.html)**  
  Replace "Statistical Framework" section (Beta Distribution Modeling, LRT, Normal Approximation, Automatic Method Selection table) with ECDF-only and Mann-Whitney U. Update summary table that mentions "LRT/Normal Approx" to "ECDF / Mann-Whitney U". No mention of Beta, LRT, or Normal.
- **[packages/methyldetector/docs/MethylDetector.html](packages/methyldetector/docs/MethylDetector.html)**  
  Replace "Beta distribution modeling with LRT and normal approximation methods" with "ECDF-based comparison and Mann-Whitney U significance testing". Replace "Likelihood ratio test computation" with ECDF/effect_size. No mention of removed features.

### 2.2 Markdown docs

- **[packages/methyldetector/README.md](packages/methyldetector/README.md)**  
  Remove all mentions of EAT, alpha1/beta1/alpha2/beta2 in export, and any "Beta" or "legacy" classifier. Export column list must not include alpha/beta. Remove enable_eat_transform from any config examples. Do not add deprecation notes.
- **[packages/methyldetector/docs/METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md](packages/methyldetector/docs/METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md)**  
  Use ECDF and Mann-Whitney U only; remove every reference to LRT, Beta, Normal, BMM, and bmm_refine_* config. Delete the BMM config examples and any "deprecated" wording.
- **[packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md](packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md)**  
  Remove alpha1/beta1/alpha2/beta2 and EAT from column list and pipeline description. Remove compute_eat_T and EAT reweighting from the pipeline. State ECDF-only; no mention of removed options.
- **[packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md](packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md)** and **.tex**  
  Remove EAT reweighting (e.g. line 57). Ensure no LRT or Normal approximation for the main test. No mention of alpha/beta or EAT.
- **[packages/methyldetector/docs/CLASSIFIER_WEIGHTS_AND_ACCURACY.md](packages/methyldetector/docs/CLASSIFIER_WEIGHTS_AND_ACCURACY.md)**  
  Remove all EAT and eat_effect_weight references. Describe only effect_size (ECDF-based) for classifier weights.
- **[packages/methyldetector/EXPORT_THREE_STAGES.md](packages/methyldetector/EXPORT_THREE_STAGES.md)**  
  Remove alpha1, beta1, alpha2, beta2 from export column list. Use "ECDF-based overlap" where overlap is described. No EAT mention.
- **[packages/methyldetector/QUICKSTART.md](packages/methyldetector/QUICKSTART.md)**  
  Remove "Beta parameters: alpha1, beta1, alpha2, beta2" from the list. Do not mention removed features.

### 2.3 Config and example docs

- **[packages/methyldetector/configs/pb-hc1-1_config_ANALYSIS.md](packages/methyldetector/configs/pb-hc1-1_config_ANALYSIS.md)**  
  Use only `classifier_type: "ecdf"` in examples; remove any "beta" classifier recommendation. No "legacy" or "deprecated" notes.
- **[packages/methyldetector/examples/README.md](packages/methyldetector/examples/README.md)**  
  Remove BMM refinement bullets and all bmm_refine_* options. Do not mention BMM.
- **[packages/methyldetector/configs/README.md](packages/methyldetector/configs/README.md)**  
  Remove every row for bmm_refine_*, EAT (enable_eat_transform, eat_*), and any obsolete detection options. Document only options that exist in the simplified config. No deprecation section.

---

## 3. Simplify JSON configuration files

Detection config in project JSONs should only include options the detector uses. No backward-compatibility keys.

- **Audit** all JSON configs that supply `step_config.detection` (or equivalent detection section): under [configs/](configs/) (e.g. project_Healthy_vs_PCa1-4.json, project_healthy_vs_prostate-4.json, project_Exp_01a.json, project_Exp_01b.json, project_PCa_vs_Healthy.json) and any under [packages/methyldetector/](packages/methyldetector/) if present.
- **Remove** from every detection block (if present): `enable_eat_transform`, `eat_gamma`, `eat_clip_t`, `eat_normalization`, `eat_low_tau_threshold`, `classifier_type` (optional: omit entirely if the only valid value is `"ecdf"` and it is the default), and any `bmm_refine_*` keys. Do not leave these keys or add "deprecated" comments in JSON.
- **Result**: Detection sections in JSON contain only current options (alpha, contexts, centroid paths, effect_size_*, validation_*, optimization_*, etc.). Docs that list detection config (e.g. configs/README.md, QUICKSTART) describe only this simplified set.

---

## 4. Tests

- **[packages/methyldetector/tests/test_ecdf_only_runtime.py](packages/methyldetector/tests/test_ecdf_only_runtime.py)**  
  Keep the test that rejects legacy keys (e.g. `"distribution": "beta"`). If any test or fixture sets `enable_eat_transform` or other removed options, remove those settings so tests run with the simplified config.

---

## 5. Summary of changes

| Area | Action |
|------|--------|
| Config | Remove entire EAT section (enable_eat_transform, eat_gamma, eat_clip_t, eat_normalization, eat_low_tau_threshold) and eat_normalization validator. |
| Core | Remove EAT import and usage, _apply_eat_transformation, eat_effect_weight from effect_size; remove alpha1/beta1/alpha2/beta2 from export columns and dtypes; replace np.random.beta in mock data with uniform. |
| MethylDetector_Theory.html | Replace Beta/LRT/Normal sections with ECDF + Mann-Whitney U; update summary table. No mention of removed features. |
| MethylDetector.html | Replace Beta/LRT wording with ECDF and Mann-Whitney U. No mention of removed features. |
| METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md | LRT → Mann-Whitney; remove all BMM and bmm_refine_* references. No deprecation notes. |
| METHYLDETECTOR_IMPLEMENTATION.md | Remove EAT and alpha/beta from pipeline and column list. State ECDF-only. |
| EXPORT_THREE_STAGES.md, QUICKSTART.md, README.md | Remove alpha/beta from export list and EAT mentions. No mention of removed features. |
| MethylDetector_Theoretical_Foundation.md/.tex, CLASSIFIER_WEIGHTS_AND_ACCURACY.md | Remove EAT references; ECDF-only. |
| pb-hc1-1_config_ANALYSIS.md | Use classifier_type "ecdf" only; remove "beta" classifier. |
| examples/README.md, configs/README.md | Remove BMM and bmm_refine_*; document only existing detection options. No deprecation section. |
| JSON configs (configs/*.json) | Strip from detection blocks: enable_eat_transform, eat_*, classifier_type (or keep only "ecdf"), bmm_refine_*. Only current options remain. |

Clean break: removed features are not exported and not mentioned in documentation. Config files are simplified with no obsolete keys.
