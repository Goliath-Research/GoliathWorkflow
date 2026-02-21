# MethylPredictor

Run MethylClassifier on test sample sets and compute classification metrics.

Part of the [MethylPipeline](https://github.com/epimethyl/MethylPipeline) monorepo.

## Installation

From the MethylPipeline repo root (install methylutils and methylclassifier first):

```bash
pip install -e packages/methylpredictor
```

## Usage

```bash
methyl-predictor --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json
```

Use `--help` for options.
