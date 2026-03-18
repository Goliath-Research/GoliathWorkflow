"""Regression tests for validation split and metrics summaries."""

import math

from methyl_validation.split import stratified_split
from methyl_validation.validator_metrics import build_metrics_table, compute_resource_summary, compute_summary


def test_stratified_split_is_reproducible_and_exhaustive():
    control_paths = [f"/samples/control_{i}" for i in range(4)]
    disease_paths = [f"/samples/disease_{i}" for i in range(6)]

    split_a = stratified_split(control_paths, disease_paths, train_fraction=0.5, seed=7)
    split_b = stratified_split(control_paths, disease_paths, train_fraction=0.5, seed=7)

    assert split_a == split_b

    train_control, train_disease, val_control, val_disease = split_a
    assert len(train_control) == 2
    assert len(val_control) == 2
    assert len(train_disease) == 3
    assert len(val_disease) == 3
    assert sorted(train_control + val_control) == sorted(control_paths)
    assert sorted(train_disease + val_disease) == sorted(disease_paths)


def test_validation_metric_summaries_aggregate_runs():
    records = [
        {"iteration": 1, "accuracy": 1.0, "balanced_accuracy": 0.90, "sensitivity": 0.80, "specificity": 1.00},
        {"iteration": 2, "accuracy": 0.8, "balanced_accuracy": 0.70, "sensitivity": 0.60, "specificity": 0.80},
        {"iteration": 3, "accuracy": 0.9, "balanced_accuracy": 0.80, "sensitivity": 0.70, "specificity": 0.90},
    ]
    metrics_df = build_metrics_table(records)
    summary = compute_summary(metrics_df)

    assert math.isclose(summary["accuracy"]["mean"], 0.9)
    assert math.isclose(summary["balanced_accuracy"]["percentiles"]["p50"], 0.8)
    assert math.isclose(summary["sensitivity"]["max"], 0.8)
    assert math.isclose(summary["specificity"]["min"], 0.8)

    resource_summary = compute_resource_summary(
        [
            {
                "run_id": "run-1",
                "step_name": "predictor",
                "duration_seconds": 4.0,
                "n_train_samples": 10,
                "n_val_samples": 4,
                "max_rss_mb": 512.0,
            },
            {
                "run_id": "run-2",
                "step_name": "predictor",
                "duration_seconds": 6.0,
                "n_train_samples": 12,
                "n_val_samples": 4,
                "max_rss_mb": 768.0,
            },
        ]
    )

    assert resource_summary["per_step_duration_seconds"]["predictor"]["count"] == 2
    assert math.isclose(
        resource_summary["per_step_duration_seconds"]["predictor"]["mean_seconds"],
        5.0,
    )
    assert resource_summary["per_iteration_total_seconds"]["n_iterations"] == 2
    assert math.isclose(resource_summary["sample_sizes"]["n_train_samples"]["mean"], 11.0)
    assert math.isclose(resource_summary["sample_sizes"]["n_val_samples"]["mean"], 4.0)
