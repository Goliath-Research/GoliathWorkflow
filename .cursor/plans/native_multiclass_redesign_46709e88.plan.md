---
name: native multiclass redesign
overview: Replace the fragile OvR-fusion approach with a supported native multiclass model built from merged per-comparison DMP tables, effect sizes, and class centroids, while keeping the current predictor loading path intact.
todos:
  - id: audit-legacy-builder
    content: Audit the existing multiclass builder and define the supported native multiclass package contract.
    status: pending
  - id: design-feature-table
    content: Design and implement a multiclass DMP feature table that preserves per-comparison effect-size information.
    status: pending
  - id: implement-native-model
    content: Implement a first native multiclass scorer using centroid parameters and effect-size-aware weights.
    status: pending
  - id: wire-export-path
    content: Add project/CLI export support for the native multiclass PKL without changing predictor inputs.
    status: pending
  - id: benchmark-vs-ovr
    content: Benchmark the native model against the current OvR pipeline on the 5-cohort validation set and document the outcome.
    status: pending
isProject: false
---

# Native Multiclass Redesign

## Goal

Build a native multiclass classifier that scores all classes on the same union DMP set, using per-comparison DMP statistics and class centroids, instead of relying on K pairwise ECDF heads plus fusion.

## Why This Path

The current max-contrast fix removes aggregate-control double counting, but your latest run still collapses to class 0. That suggests the remaining problem is the underlying multiclass formulation, not just the fusion rule.

Two existing hooks make this redesign practical:

```41:49:packages/methyldetector/methyl_detector/utils/multiclass_merge.py
Read all dmps-*.csv from each detection dir, union by (chromosome, context, position),
and write one merged CSV. For duplicate positions, keep the row with highest weight
(effect_size/importance/weight) if present.
```

```659:718:packages/methylclassifier/methyl_classifier/core/classifier.py
elif isinstance(model_package, dict) and 'classifier' in model_package:
    self.classifier = model_package['classifier']
    self.metadata = model_package.get('metadata', {})
    ...
    if "dmp_df" in model_package:
        self.dmp_positions_df = dmp_df[["chromosome", "position"]].copy()
```

That means the main work is in training/export, not in reworking MethylPredictor.

## Proposed Direction

Default implementation: replace the stale legacy path in [packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py](packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py) with a supported native multiclass package that:

- starts from the union of per-comparison DMP CSVs under [packages/methyldetector/methyl_detector/utils/multiclass_merge.py](packages/methyldetector/methyl_detector/utils/multiclass_merge.py)
- preserves multiclass provenance instead of keeping only the single max-effect row per site
- looks up per-class centroid parameters from H5s via [packages/methylclassifier/methyl_classifier/project_resolver.py](packages/methylclassifier/methyl_classifier/project_resolver.py)
- scores every class directly on the same feature set, with effect-size-aware weights
- exports a single-file package that [packages/methylclassifier/methyl_classifier/core/classifier.py](packages/methylclassifier/methyl_classifier/core/classifier.py) and [packages/methylpredictor/methyl_predictor/core/predictor.py](packages/methylpredictor/methyl_predictor/core/predictor.py) can already load

```mermaid
flowchart LR
    detectorDirs[PerComparisonDmpCsvs] --> featureTable[MulticlassFeatureTable]
    featureTable --> centroidLookup[PerClassCentroidParams]
    centroidLookup --> nativeModel[NativeMulticlassScorer]
    nativeModel --> modelPkl[SingleFileMulticlassPkl]
    modelPkl --> predictor[MethylPredictor]
```



## Work Plan

1. Audit and retire the broken legacy builder path.
  Default assumption: do not revive `MultiClassBetaMixtureClassifier` as-is. The current builder references a legacy classifier path and is the wrong place to hang new production behavior without first defining a supported classifier contract.
2. Upgrade the merged DMP artifact from a plain max-effect union into a multiclass feature table.
  Extend the merge stage so each retained DMP carries enough multiclass signal for training: source comparison label, effect size, signed delta, and a stable aggregation rule when the same site appears in multiple comparisons. This should live next to [packages/methyldetector/methyl_detector/utils/multiclass_merge.py](packages/methyldetector/methyl_detector/utils/multiclass_merge.py), not as ad hoc notebook logic.
3. Implement a first native multiclass scorer using class centroids plus effect-size weights.
  Baseline choice: a weighted generative scorer over the union DMP table, where each class is scored directly from its centroid parameters on the same positions. Keep the first version simple and auditable rather than jumping straight to a complex stacked model.
4. Package the model as a standard single-file classifier artifact.
  Reuse the existing `{"classifier": ..., "dmp_df": ..., "metadata": ...}` load contract in [packages/methylclassifier/methyl_classifier/core/classifier.py](packages/methylclassifier/methyl_classifier/core/classifier.py) so prediction code remains stable.
5. Wire project-level training/export.
  Extend the project resolver and CLI flow so a control/disease project can build the multiclass feature table and export the native multiclass PKL directly, alongside or instead of the current OvR bundle.
6. Add side-by-side evaluation against OvR.
  On the same 5-cohort project, compare native multiclass vs current OvR using centroid validation, balanced accuracy, macro F1, and per-class probability separation. Keep the current OvR path as the baseline until the native model clearly beats it.
7. Document the model contract and workflow.
  Update the classifier and predictor docs so it is clear when to use native multiclass vs OvR, what artifact gets exported, and what metrics should be checked before trusting a new bundle.

## Key Files

- [packages/methyldetector/methyl_detector/utils/multiclass_merge.py](packages/methyldetector/methyl_detector/utils/multiclass_merge.py)
- [packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py](packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py)
- [packages/methylclassifier/methyl_classifier/project_resolver.py](packages/methylclassifier/methyl_classifier/project_resolver.py)
- [packages/methylclassifier/methyl_classifier/core/classifier.py](packages/methylclassifier/methyl_classifier/core/classifier.py)
- [packages/methylpredictor/methyl_predictor/core/predictor.py](packages/methylpredictor/methyl_predictor/core/predictor.py)
- [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)
- [packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py)

## Success Criteria

- Native multiclass training produces a single PKL loadable by current predictor code.
- The feature table preserves multiclass effect-size information instead of collapsing to only one winning comparison per site.
- On the 5-cohort validation setup, the native model materially improves over the current OvR baseline on disease classes, not just overall accuracy driven by the healthy cohort.

