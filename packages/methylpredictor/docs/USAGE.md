# MethylPredictor Usage Guide

## Overview

MethylPredictor runs a trained **MethylClassifier** on two test sample sets—**control** (e.g. healthy) and **disease** (e.g. sick)—and reports **accuracy metrics** (accuracy, balanced accuracy, sensitivity, specificity, F1, confusion matrix, etc.). It does not train the model; it evaluates it on holdout test samples.

There are **two ways to run MethylPredictor**:

1. **Docker container** — Run inside the MethylPipeline container with dependencies provided.
2. **Local host with virtual environment** — Create a venv, install MethylUtils, MethylClassifier, and MethylPredictor, activate the venv, and run on the host.

Use one or the other; the CLI and behavior are the same once the environment is active.

---

## Setup 1: Docker container

Use this when you want a reproducible environment (e.g. same as MethylCentroid/MethylDetector/MethylClassifier).

**Prerequisites:** Docker; for GPU (if used), NVIDIA Container Toolkit.

**1. Start the container**

From the MethylPipeline repo:

```bash
cd /path/to/MethylPipeline/docker
docker compose up -d
```

(Use the same container name as in your compose file; below assumes `methylpipeline` and repo mounted at `/workspace`.)

**2. Run MethylPredictor**

Paths in your config or arguments must be valid **inside** the container (e.g. `/workspace/...`). From the host:

```bash
docker exec -w /workspace methylpipeline \
  methyl-predictor --project /workspace/configs/project.json
```

Or with explicit model and test sets:

```bash
docker exec -w /workspace methylpipeline \
  methyl-predictor --model-dir /workspace/classifiers/PCa_vs_Healthy \
    --output-dir /workspace/out \
    --test-control /workspace/test/control.csv \
    --test-disease /workspace/test/disease.csv
```

**Common options:** `--project`, `--config`, `--model`, `--model-dir`, `--output-dir`, `--test-control`, `--test-disease`, `--step-override`, `--per-comparison`, `--debug`. Paths must be container paths (e.g. `/workspace/...`).

---

## Setup 2: Local host with virtual environment

Use this when you run on the host and want to activate a virtual environment before running MethylPredictor.

**Prerequisites:** Python 3.8+.

**1. Create a virtual environment**

```bash
python3 -m venv venv
```

**2. Activate the virtual environment**

```bash
source ./venv/bin/activate
```

On Windows: `venv\Scripts\activate`. After activation, the prompt usually shows `(venv)`.

**3. Install MethylUtils (required by MethylClassifier)**

MethylPredictor depends on MethylClassifier, which depends on MethylUtils. Install MethylUtils first:

```bash
cd /path/to/MethylPipeline/packages/methylutils
pip install -e .
```

**4. Install MethylClassifier**

```bash
cd /path/to/MethylPipeline/packages/methylclassifier
pip install -e .
```

**5. Install MethylPredictor**

```bash
cd /path/to/MethylPipeline/packages/methylpredictor
pip install -e .
```

**6. Run MethylPredictor**

With the virtual environment **activated** (`source ./venv/bin/activate`), use the CLI. Paths are on the **host**; you do not use a container.

```bash
methyl-predictor --project configs/project.json
methyl-predictor --model-dir /path/to/classifiers/PCa_vs_Healthy \
  --output-dir ./out \
  --test-control test/control.csv \
  --test-disease test/disease.csv
```

---

## Specifying test samples (healthy and disease groups)

MethylPredictor needs two sets of sample paths: **control** (expected class 0, e.g. healthy) and **disease** (expected class 1, e.g. sick). Each sample is a directory (or path) that MethylClassifier can load (same format as for MethylClassifier input).

**Ways to specify test sets:**

| Source | Control paths | Disease paths |
|--------|----------------|---------------|
| **Project** | `step_config.predictor.test_control_paths` | `step_config.predictor.test_disease_paths` |
| **Config JSON** | `test_control_paths` (array of strings) | `test_disease_paths` (array of strings) |
| **CLI** | `--test-control` | `--test-disease` |

**`--test-control` and `--test-disease`** accept either:

- A **CSV file path**: CSV must have a column named `path`, `sample`, or `sample_path` (or the first column is used). Each row is one sample path.
- **Comma-separated paths**: e.g. `--test-control /data/s1,/data/s2,/data/s3`.

Examples:

```bash
# CSV files listing sample directories
methyl-predictor --model-dir ./classifiers --output-dir ./out \
  --test-control ./test_lists/healthy.csv --test-disease ./test_lists/sick.csv

# Inline paths
methyl-predictor --model-dir ./classifiers --output-dir ./out \
  --test-control /data/healthy1,/data/healthy2 \
  --test-disease /data/sick1,/data/sick2
```

Samples should be **holdout** (not used for training) so that reported metrics reflect generalization.

---

## Accuracy metrics reported

MethylPredictor computes several accuracy metrics for the test samples (healthy and disease groups) and writes them to **validation_metrics.json** and prints a short summary to the console.

### Global metrics

| Metric | Description |
|--------|-------------|
| **accuracy** | Proportion of correct predictions over all test samples. |
| **balanced_accuracy** | Mean of per-class recall; for binary, (sensitivity + specificity) / 2. Prefer this when test set is imbalanced. |
| **confusion_matrix** | Rows = true class (0 = control, 1 = disease), columns = predicted class. |
| **n_samples** | Total number of test samples. |
| **n_classes** | Number of classes (2 for binary). |
| **class_names** | Names for each class (e.g. control, disease). |

### Per-class metrics (for each of control and disease)

| Metric | Description |
|--------|-------------|
| **precision** | For that class: predicted positives that are truly that class. |
| **recall** | For that class: true members of that class that were predicted as that class. |
| **f1** | Harmonic mean of precision and recall for that class. |
| **support** | Number of test samples in that class. |

### Binary (2-class) metrics

When the classifier is binary (control vs disease), MethylPredictor also reports:

| Metric | Description |
|--------|-------------|
| **sensitivity** | Recall for class 1 (disease): fraction of disease samples correctly predicted as disease. |
| **specificity** | Recall for class 0 (control): fraction of control samples correctly predicted as control. |
| **precision_binary** | Precision for the positive class (disease). |
| **recall_binary** | Same as sensitivity. |
| **f1_binary** | F1 for the positive class (disease). |

### Macro / weighted

| Metric | Description |
|--------|-------------|
| **macro_precision** | Mean of per-class precision. |
| **macro_recall** | Mean of per-class recall. |
| **macro_f1** | Mean of per-class F1. |
| **weighted_f1** | F1 averaged by support (weighted by class size). |

### Where to find the metrics

- **validation_metrics.json** (in `output_dir`): Full JSON-serializable dict with all metrics above. Use this for downstream scripts or reporting.
- **Console**: A short summary is printed after the run (accuracy, balanced accuracy, sensitivity, specificity, confusion matrix).

---

## Output files

| File | Description |
|------|-------------|
| **validation_metrics.json** | All metrics (accuracy, balanced_accuracy, confusion_matrix, per_class, sensitivity, specificity, etc.). |
| **predictions.csv** | One row per test sample: sample identifier, expected_class (0 or 1), prediction, and any probability columns produced by MethylClassifier. |

Both are written to the directory given by `--output-dir` or `output_dir` in config/project.

---

## Related documentation

- [MethylPredictor Theoretical Foundation](MethylPredictor_Theoretical_Foundation.md) — Goal, test sets, and metric definitions.
- [METHYLPREDICTOR_IMPLEMENTATION](METHYLPREDICTOR_IMPLEMENTATION.md) — How MethylPredictor uses MethylClassifier and computes metrics.
