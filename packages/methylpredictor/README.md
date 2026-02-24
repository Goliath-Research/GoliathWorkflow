# MethylPredictor

Run MethylClassifier on test sample sets (control and disease) and compute **accuracy metrics** (accuracy, balanced accuracy, sensitivity, specificity, F1, confusion matrix, etc.).

Part of the [MethylPipeline](https://github.com/epimethyl/MethylPipeline) monorepo.

## Installation

From the MethylPipeline repo root (install MethylUtils and MethylClassifier first):

```bash
pip install -e packages/methylutils/methyl_utils
pip install -e packages/methylclassifier
pip install -e packages/methylpredictor
```

## Usage

```bash
methyl-predictor --project configs/project.json
methyl-predictor --model-dir /path/to/classifiers --output-dir ./out \
  --test-control test/control.csv --test-disease test/disease.csv
```

Use `--help` for options.

## Documentation

- **[Usage Guide (Docker & venv)](docs/USAGE.md)** — Setup (Docker / virtual environment), specifying test samples (healthy and disease groups), and **accuracy metrics reported**.
- [Theoretical Foundation](docs/MethylPredictor_Theoretical_Foundation.md) — Goal, test sets, and metric definitions.
- [Implementation](docs/METHYLPREDICTOR_IMPLEMENTATION.md) — How MethylPredictor uses MethylClassifier and computes metrics.
