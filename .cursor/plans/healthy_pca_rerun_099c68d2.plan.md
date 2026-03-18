---
name: Healthy PCa Rerun
overview: Run a full post-revision verification of the `Healthy_vs_PCa1-4` workflow with live Grok enrichment, then validate each binary comparison through Monte Carlo runs anchored to the same base project.
todos:
  - id: preflight-env
    content: Validate GROK auth, sample/GTF inputs, and setup prerequisites for the Healthy_vs_PCa1-4 rerun.
    status: pending
  - id: rerun-core-pipeline
    content: Run the full project-driven centroid -> detector -> mapper -> enricher -> classifier -> predictor chain from project_Healthy_vs_PCa1-4.json.
    status: pending
  - id: audit-detector-selection
    content: Inspect detector biological DMP exports, classifier cap behavior, and centroid self-check output for each comparison.
    status: pending
  - id: verify-downstream-metrics
    content: Confirm downstream mapper/enricher/classifier/predictor artifacts and summarize holdout metrics for pca1-pca4.
    status: pending
  - id: run-monte-carlo
    content: Execute the existing per-disease Monte Carlo validation configs anchored to the revised base project and collect aggregate metrics.
    status: pending
  - id: final-acceptance
    content: Compile a final compatibility report covering core pipeline health, biological DMP behavior, enrichment auth, and validation outcomes.
    status: pending
isProject: false
---

# Healthy-vs-PCa Rerun

## Scope

- Base project: [configs/project_Healthy_vs_PCa1-4.json](/home/ubuntu/MethylPipeline/configs/project_Healthy_vs_PCa1-4.json)
- Include the full project-driven chain and Monte Carlo validation.
- Keep mapper disease enrichment live via `GROK_API_KEY`.
- Reuse the existing binary Monte Carlo templates: [configs/monte_carlo_Healthy_vs_PCa1.json](/home/ubuntu/MethylPipeline/configs/monte_carlo_Healthy_vs_PCa1.json), [configs/monte_carlo_Healthy_vs_PCa2.json](/home/ubuntu/MethylPipeline/configs/monte_carlo_Healthy_vs_PCa2.json), [configs/monte_carlo_Healthy_vs_PCa3.json](/home/ubuntu/MethylPipeline/configs/monte_carlo_Healthy_vs_PCa3.json), and [configs/monte_carlo_Healthy_vs_PCa4.json](/home/ubuntu/MethylPipeline/configs/monte_carlo_Healthy_vs_PCa4.json).

## Critical checks

- The current project config already encodes the detector behavior you want to verify in [configs/project_Healthy_vs_PCa1-4.json](/home/ubuntu/MethylPipeline/configs/project_Healthy_vs_PCa1-4.json): `effect_size_coverage=0.95`, `effect_size_weight_power=3.0`, `max_dmps_for_classifier=15000`, and `centroid_self_check_top_k=5000`.
- The active detector implementation in [packages/methyldetector/methyl_detector/core/methyldetector.py](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py), [packages/methyldetector/methyl_detector/models/config.py](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/models/config.py), and [packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md](/home/ubuntu/MethylPipeline/packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md) now does three distinct things that the rerun must confirm:
- It keeps the minimum per-context prefix whose cumulative `effect_size` reaches `effect_size_coverage`.
- It exports the biological funnel sorted by `effect_size`.
- It caps the classifier handoff separately with `max_dmps_for_classifier`, while the centroid self-check can use only the top `K` loci by `effect_size`.

## Execution plan

1. Preflight the environment and external dependencies.

- Verify the sample CSVs referenced by the base project and predictor test sets exist.
- Verify the GTF path in the mapper step exists.
- Export `GROK_API_KEY` in the shell that will run mapper and enricher.
- Run [scripts/verify_setup.sh](/home/ubuntu/MethylPipeline/scripts/verify_setup.sh) to confirm the repo, package installs, GPU tooling, `bedtools`, and docs/scripts layout are still coherent after the revision.

1. Rerun the full project-driven pipeline from the revised base project.

- Use the canonical sequence from [docs/OPERATIONS_MANUAL.md](/home/ubuntu/MethylPipeline/docs/OPERATIONS_MANUAL.md): `methyl-centroid --project ... --group all`, then `methyl-detector`, `methyl-mapper`, `methyl-enricher`, `methyl-classifier`, and `methyl-predictor` with the same project file.
- Because this project uses `controls`/`diseases`/`comparisons`, the downstream steps will resolve per-comparison output directories automatically under `detections/<control>/<disease>`, `mapper/<control>/<disease>`, `enricher/<control>/<disease>`, `classifiers/<control>/<disease>`, and `predictors/<control>/<disease>`.

1. Audit MethylDetector specifically for the prior training-selection concern.

- For each comparison and chromosome, inspect the detector outputs under the project root and compare `results-{chrom}.json` with the exported `dmps-{chrom}-biological-sorted.csv`.
- Confirm that `total_biological_dmps` reflects the full biological funnel while the classifier build respects `max_dmps_for_classifier`.
- Confirm the logs do not report centroid self-check failure, especially the historical `both centroids classify as class0` warning.
- If the retained DMP set still looks too diffuse, use the existing `filter_funnel_explore.effect_size_coverage` output as the first diagnostic before changing thresholds; only then consider narrowing `effect_size_coverage` or increasing `effect_size_weight_power` in a follow-up pass.

1. Verify downstream outputs and holdout metrics per comparison.

- Check that mapper and enricher complete for all four comparisons and that live disease enrichment succeeds with `GROK_API_KEY`.
- Check that each comparison gets its classifier artifact and predictor output, including `validation_metrics.json` under the per-comparison predictor directory.
- Summarize balanced accuracy, sensitivity, and specificity across `pca1` through `pca4` using the shared predictor holdouts currently defined in the base project.

1. Run Monte Carlo validation for each binary comparison.

- Use the existing Monte Carlo configs as the validation entrypoints because [packages/methylvalidation/methyl_validation/cli.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py) and [packages/methylvalidation/methyl_validation/config.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py) still require a separate `base_project`-driven validation config and the runner is binary-only per run.
- Execute one validation run set for each disease group (`PCa1` to `PCa4`) and collect `all_metrics.csv`, `metrics_summary.json`, `step_timings.csv`, and `resource_summary.json` from each `monte_carlo_runs` tree.

1. Produce a final acceptance summary.

- For each comparison, record centroid build health, detector biological DMP counts, self-check status, classifier creation, predictor metrics, mapper/enricher success, and Monte Carlo metric distributions.
- Treat any of the following as blockers for a “compatible after revision” conclusion: missing Grok-authenticated enrichment, detector self-check failure, classifier export missing for a comparison, or materially degraded predictor / Monte Carlo metrics.

