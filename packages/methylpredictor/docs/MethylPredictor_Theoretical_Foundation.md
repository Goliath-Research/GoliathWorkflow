# MethylPredictor Theoretical Foundation

## Goal

MethylPredictor evaluates a trained classifier (from MethylDetector/MethylClassifier) on **holdout test samples** in two groups: **control** (e.g. healthy, class 0) and **disease** (e.g. sick, class 1). It does not train or modify the model; it runs classification on the test sets and computes **classification metrics** to report how well the model generalizes.

## Role in the Pipeline

- **MethylCentroid**: Builds centroids per group.
- **MethylDetector**: Detects DMPs and trains a classifier (e.g. binary healthy vs disease).
- **MethylClassifier**: Loads the classifier and predicts on new samples.
- **MethylPredictor**: Runs MethylClassifier on **designated test sample sets** (control and disease), compares predictions to the known labels (control → 0, disease → 1), and reports **accuracy metrics**.

So the “theory” behind MethylPredictor is standard **supervised evaluation**: given a classifier and labeled test sets, compute metrics that measure classification performance (accuracy, balanced accuracy, sensitivity, specificity, etc.).

## Test Sets and Labels

- **test_control_paths**: Sample directories (or paths from a CSV) for the **control** group. These are assigned **expected class 0**.
- **test_disease_paths**: Sample directories (or paths from a CSV) for the **disease** group. These are assigned **expected class 1**.

Samples should be **independent** of the data used to build centroids and train the classifier (true holdout) so that reported metrics reflect generalization.

## Metrics Reported

MethylPredictor uses **scikit-learn** and standard definitions:

- **Accuracy**: Proportion of correct predictions overall.
- **Balanced accuracy**: Mean of per-class recall (for binary: (sensitivity + specificity) / 2). Appropriate for imbalanced test sets.
- **Confusion matrix**: Rows = true class, columns = predicted class.
- **Per-class**: Precision, recall, F1, support (count) for each class (control and disease).
- **Binary (2-class)**: Sensitivity (recall for class 1, i.e. disease), specificity (recall for class 0, i.e. control), plus precision/recall/F1 for the positive class.
- **Macro/weighted**: Macro-averaged precision, recall, F1; weighted F1 by support.

All of these are written to **validation_metrics.json** and summarized in the console. For multiclass models, the same structure applies with more classes.

## Summary

| Aspect | Role |
|--------|------|
| Input | Trained classifier (model_dir or model_path), test_control_paths, test_disease_paths |
| Labels | Control → 0, disease → 1 (fixed by group membership) |
| Output | validation_metrics.json (all metrics), predictions.csv (per-sample predictions and expected class) |
| Theory | Standard classification evaluation; no new probabilistic model |

For how the classifier itself works (Beta likelihoods, posterior), see MethylClassifier documentation. For implementation details (MethylClassifier, metrics computation), see [METHYLPREDICTOR_IMPLEMENTATION.md](METHYLPREDICTOR_IMPLEMENTATION.md).
