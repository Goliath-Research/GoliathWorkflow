# Unified Project Config Guide

This document is the single repository-level reference for the project JSON consumed by the project-aware MethylPipeline CLIs.

The code-level source of truth is `packages/methylutils/methyl_utils/pipeline_config.py`.

## Goal

One project JSON should be enough to drive:

- centroid building
- detector runs
- mapper and enricher runs
- classifier and predictor runs
- optional alignment QC and clustering

The supported schema is `controls` / `diseases` / `comparisons`.

## Canonical Shape

```json
{
  "project_name": "PCa_vs_Healthy",
  "output_base": "/data/out",
  "samples_base_path": "/data/samples",
  "controls": {
    "label": "healthy",
    "groups": [
      { "label": "healthy", "sample_paths": ["configs/healthy.csv"] }
    ]
  },
  "diseases": {
    "label": "cancer",
    "groups": [
      { "label": "cancer", "sample_paths": ["configs/cancer.csv"] }
    ]
  },
  "comparisons": [
    { "control_group": "healthy", "disease_group": "cancer" }
  ],
  "chromosomes": ["1", "2", "X"],
  "contexts": ["CG"],
  "path_remap": {
    "/old/root": "/new/root"
  },
  "step_config": {
    "centroid": {},
    "detection": {},
    "mapper": {},
    "enricher": {},
    "classifier": {},
    "predictor": {},
    "alignment_qc": {},
    "cluster": {}
  }
}
```

## Top-Level Fields

| Field | Required | Meaning |
|-------|----------|---------|
| `project_name` | yes | Project identifier used under `output_base`. |
| `output_base` | yes | Root output parent directory. |
| `controls` | yes | Control side definition with a side label and one or more groups. |
| `diseases` | yes | Disease side definition with a side label and one or more groups. |
| `comparisons` | yes | Explicit control/disease pairs to run downstream. |
| `samples_base_path` | no | Base path for sample names listed in CSV / TXT files. |
| `chromosomes` | no | Shared chromosome list. |
| `contexts` | no | Shared methylation contexts. |
| `path_remap` | no | Prefix replacement map for moved sample paths. |
| `step_config` | no | Per-step defaults merged by the package resolvers. |

## Controls, Diseases, and Groups

Each side has:

- `label`: the side label used in centroid directory layout
- `groups`: one or more biological groups under that side

Each group has:

- `label`
- `sample_paths`
- optional `level_labels_path`
- optional `samples_base_path`
- optional `subcluster`

Example:

```json
"controls": {
  "label": "healthy",
  "groups": [
    { "label": "all", "sample_paths": ["configs/healthy.csv"] }
  ]
},
"diseases": {
  "label": "cancer",
  "groups": [
    { "label": "pca1", "sample_paths": ["configs/pca1.csv"] },
    { "label": "pca2", "sample_paths": ["configs/pca2.csv"] }
  ]
}
```

## Comparisons

`comparisons` defines which downstream control/disease pairs to run.

Example:

```json
"comparisons": [
  { "control_group": "all", "disease_group": "pca1" },
  { "control_group": "all", "disease_group": "pca2" }
]
```

Optional:

- `comparison_label`

The loader also accepts comparison shorthands:

- `"control_vs_each_disease"`
- `"all_pairs"`

## Output Layout

Let:

- `project_root = {output_base}/{project_name}`

Then the canonical paths are:

```text
{project_root}/
├── centroids/
│   ├── controls/<control-side-label>/<group>/
│   └── diseases/<disease-side-label>/<group>/
├── detections/<control_group>/<disease_group>/
├── mapper/<control_group>/<disease_group>/
├── enricher/<control_group>/<disease_group>/
├── classifiers/<control_group>/<disease_group>/
├── predictors/<control_group>/<disease_group>/
├── alignment_qc/
└── clustering/
```

Important:

- centroid paths are side-oriented
- detector, mapper, enricher, classifier, and predictor paths are comparison-oriented
- do not document or hardcode older `detection/cancer/<group>` or `classifier/cancer/<group>` layouts as the primary contract

## Sample Path Resolution

`sample_paths` entries may be:

- direct sample directory paths
- `.txt` files with one path or sample name per line
- `.csv` files with a `sample`, `path`, `sample_path`, `name`, or first column
- `.json` arrays

When `samples_base_path` is set, entries inside those files may be sample folder names.

`path_remap` is applied after resolution using the longest matching prefix.

## Step Config

Supported `step_config` keys:

- `centroid`
- `detection`
- `mapper`
- `enricher`
- `classifier`
- `predictor`
- `alignment_qc`
- `cluster`

Deprecated compatibility:

- `validator` is normalized to `predictor`

Typical uses:

- `step_config.detection.contexts`
- `step_config.mapper.gtf`
- `step_config.predictor.test_control_paths`
- `step_config.classifier.weight_method`

Secrets should come from the environment or a local override file, not from the tracked project JSON.

## CLI Usage

Typical project-driven run:

```bash
methyl-centroid --project configs/project_PCa_vs_Healthy.json --group all
methyl-detector --project configs/project_PCa_vs_Healthy.json
methyl-mapper --project configs/project_PCa_vs_Healthy.json
methyl-enricher --project configs/project_PCa_vs_Healthy.json
methyl-classifier --project configs/project_PCa_vs_Healthy.json
methyl-predictor --project configs/project_PCa_vs_Healthy.json
```

Monte Carlo validation uses a separate config:

```bash
methyl-validation --config configs/monte_carlo.json
```

That validation config points at a `base_project`.

## Compatibility Notes

The loader still accepts:

- `group1` / `group2`
- flat `groups`
- nested project-level keys accidentally placed inside `controls` or `diseases`
- nested legacy predictor blocks under a side

Those shapes are compatibility shims, not the preferred schema for new configs.

## Example Files

Start from these repo examples:

- `configs/project_PCa_vs_Healthy.json`
- `configs/project_Healthy_vs_PCa1-4.json`
- `configs/project_PCa1_3levels_vs_Healthy_Hardik.json`

See [configs/README.md](../configs/README.md) for a short index.
