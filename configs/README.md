# Config Examples

This directory contains repository-level project examples for the unified MethylPipeline project contract.

The main reference is [docs/UNIFIED_PROJECT_CONFIG_GUIDE.md](../docs/UNIFIED_PROJECT_CONFIG_GUIDE.md).

## Recommended Schema

Use:

- `project_name`
- `output_base`
- `controls`
- `diseases`
- `comparisons`
- optional `samples_base_path`, `chromosomes`, `contexts`, `path_remap`
- optional `step_config`

The canonical output layout is comparison-based for downstream steps:

```text
{project_root}/detections/<control_group>/<disease_group>/
{project_root}/mapper/<control_group>/<disease_group>/
{project_root}/enricher/<control_group>/<disease_group>/
{project_root}/classifiers/<control_group>/<disease_group>/
{project_root}/predictors/<control_group>/<disease_group>/
```

## Good Starting Points

- `project_PCa_vs_Healthy.json`
  - simple one-control / one-disease project
  - good template for a single binary comparison

- `project_Healthy_vs_PCa1-4.json`
  - one control group with multiple disease comparisons
  - good template for comparison-driven downstream runs

- `project_PCa1_3levels_vs_Healthy_Hardik.json`
  - multiple disease subgroups with explicit comparisons
  - includes `step_config.predictor`

## Config Practices

- Keep tracked configs free of secrets.
- Set `GROK_API_KEY` and similar credentials through the environment or local override files.
- Prefer `step_config.predictor` over the deprecated `validator` key.
- Prefer `csv_pattern: "dmps-*.csv"` for mapper examples unless you intentionally need a different detector export.

## Running With These Configs

```bash
methyl-centroid --project configs/project_PCa_vs_Healthy.json --group all
methyl-detector --project configs/project_PCa_vs_Healthy.json
methyl-mapper --project configs/project_PCa_vs_Healthy.json
methyl-enricher --project configs/project_PCa_vs_Healthy.json
methyl-classifier --project configs/project_PCa_vs_Healthy.json
methyl-predictor --project configs/project_PCa_vs_Healthy.json
```

Validation is separate:

```bash
methyl-validation --config configs/monte_carlo.json
```

That validation config should point at a `base_project`.
