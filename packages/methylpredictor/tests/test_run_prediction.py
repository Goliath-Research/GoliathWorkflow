"""Regression tests for predictor metrics, path normalization, and prediction_report.json."""

import csv
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from methyl_predictor.models.config import PredictorConfig
from methyl_predictor.core.predictor import _expand_nested_labeled_paths, run_prediction


class _DummyClassifier:
    def __init__(self, *_args, **_kwargs):
        self.n_classes = 2
        self.class_names = ["control", "disease"]
        self.is_multi_chromosome = False
        self.classifier = self

    def get_feature_info(self):
        return {"positions": [10, 20]}


class _DummyOvRClassifier:
    """Minimal stand-in for OvR-loaded MethylClassifier (no real ECDF)."""

    def __init__(self, *_args, **_kwargs):
        self.n_classes = 3
        self.class_names = ["g0", "g1", "g2"]
        self.is_multi_chromosome = False
        self.classifier = None
        self._ovr_mode = True
        self._ovr_binary_classifiers = [object(), object(), object()]
        self.dmp_positions_df = pd.DataFrame(
            {"chromosome": ["1", "1"], "position": [10, 20]}
        )

    def get_feature_info(self):
        return {"positions": np.array([10, 20], dtype=np.uint32), "n_features": 2}


def test_run_prediction_multiclass_ovr_k3_writes_validation_metrics(monkeypatch, tmp_path):
    """Labeled K=3 run with OvR-style classifier stub writes validation_metrics.json."""
    output_dir = tmp_path / "pred_ovr"
    classifier_cli_main = importlib.import_module("methyl_classifier.cli.main")
    s1 = str(tmp_path / "s1")
    s2 = str(tmp_path / "s2")
    s3 = str(tmp_path / "s3")
    config = PredictorConfig(
        model_path=str(tmp_path / "ovr.pkl"),
        output_dir=str(output_dir),
        test_group_paths=[
            {"label": "g0", "paths": [s1]},
            {"label": "g1", "paths": [s2]},
            {"label": "g2", "paths": [s3]},
        ],
        sample_lineage=[
            {"absolute_path": s1, "side": "multiclass", "group_label": "g0"},
            {"absolute_path": s2, "side": "multiclass", "group_label": "g1"},
            {"absolute_path": s3, "side": "multiclass", "group_label": "g2"},
        ],
    )

    monkeypatch.setattr(
        "methyl_classifier.core.classifier.MethylClassifier",
        _DummyOvRClassifier,
    )

    def fake_classify(*, classifier, samples_list, output_file, expected_classes, **_kwargs):
        assert samples_list == [s1, s2, s3]
        assert expected_classes == [0, 1, 2]
        with Path(output_file).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sample",
                    "prediction",
                    "expected_class",
                    "prob_class0",
                    "prob_class1",
                    "prob_class2",
                ],
            )
            writer.writeheader()
            for i, name in enumerate(["s1", "s2", "s3"]):
                p = [0.1, 0.1, 0.1]
                p[i] = 0.8
                writer.writerow(
                    {
                        "sample": name,
                        "prediction": i,
                        "expected_class": i,
                        "prob_class0": p[0],
                        "prob_class1": p[1],
                        "prob_class2": p[2],
                    }
                )

    monkeypatch.setattr(classifier_cli_main, "classify_samples_from_list", fake_classify)

    metrics = run_prediction(config)

    assert metrics["n_classes"] == 3
    assert metrics["accuracy"] == 1.0
    assert Path(output_dir / "validation_metrics.json").exists()
    vm = json.loads((output_dir / "validation_metrics.json").read_text(encoding="utf-8"))
    assert vm["n_classes"] == 3
    assert len(vm["per_class"]) == 3


def test_run_prediction_ovr_k2_uses_test_group_paths_only(monkeypatch, tmp_path):
    """Binary OvR (n_classes=2) with only test_group_paths must not fall back to empty control/disease lists."""
    output_dir = tmp_path / "pred_ovr_k2"
    classifier_cli_main = importlib.import_module("methyl_classifier.cli.main")
    s0 = str(tmp_path / "c0")
    s1 = str(tmp_path / "c1")
    config = PredictorConfig(
        model_path=str(tmp_path / "ovr2.pkl"),
        output_dir=str(output_dir),
        test_control_paths=[],
        test_disease_paths=[],
        test_group_paths=[
            {"label": "all", "paths": [s0]},
            {"label": "pca", "paths": [s1]},
        ],
        sample_lineage=[],
    )

    monkeypatch.setattr(
        "methyl_classifier.core.classifier.MethylClassifier",
        _DummyClassifier,
    )

    def fake_classify(*, classifier, samples_list, output_file, expected_classes, **_kwargs):
        assert samples_list == [s0, s1]
        assert expected_classes == [0, 1]
        with Path(output_file).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sample",
                    "prediction",
                    "expected_class",
                    "prob_class0",
                    "prob_class1",
                ],
            )
            writer.writeheader()
            for i, name in enumerate(["c0", "c1"]):
                p0, p1 = (0.8, 0.2) if i == 0 else (0.2, 0.8)
                writer.writerow(
                    {
                        "sample": name,
                        "prediction": i,
                        "expected_class": i,
                        "prob_class0": p0,
                        "prob_class1": p1,
                    }
                )

    monkeypatch.setattr(classifier_cli_main, "classify_samples_from_list", fake_classify)

    metrics = run_prediction(config)
    assert metrics["n_classes"] == 2
    assert metrics["accuracy"] == 1.0


def test_predictor_config_resolves_relative_test_paths(tmp_path):
    config = PredictorConfig(
        model_path=str(tmp_path / "classifier.pkl"),
        output_dir=str(tmp_path / "out"),
        samples_base_path=str(tmp_path / "samples"),
        test_control_paths=["ctrl_1", "ctrl_2"],
        test_disease_paths=["disease_1"],
    )

    assert config.test_control_paths == [
        str((tmp_path / "samples" / "ctrl_1").resolve()),
        str((tmp_path / "samples" / "ctrl_2").resolve()),
    ]
    assert config.test_disease_paths == [str((tmp_path / "samples" / "disease_1").resolve())]


def test_run_prediction_metrics_follow_filtered_rows(monkeypatch, tmp_path):
    output_dir = tmp_path / "predictor"
    classifier_cli_main = importlib.import_module("methyl_classifier.cli.main")
    config = PredictorConfig(
        model_path=str(tmp_path / "classifier.pkl"),
        output_dir=str(output_dir),
        test_control_paths=["/samples/c0", "/samples/c1"],
        test_disease_paths=["/samples/d0"],
        comparison_label="test_comp",
        report_controls={
            "label": "healthy",
            "groups": [{"label": "all", "sample_paths": ["configs/healthy.csv"]}],
        },
        report_diseases={
            "label": "cancer",
            "groups": [{"label": "pca1", "sample_paths": ["configs/pca1.csv"]}],
        },
        sample_lineage=[
            {"absolute_path": "/samples/c0", "side": "control", "group_label": "all"},
            {"absolute_path": "/samples/c1", "side": "control", "group_label": "all"},
            {"absolute_path": "/samples/d0", "side": "disease", "group_label": "pca1"},
        ],
    )

    monkeypatch.setattr(
        "methyl_classifier.core.classifier.MethylClassifier",
        _DummyClassifier,
    )

    def fake_classify(*, classifier, samples_list, output_file, expected_classes, **_kwargs):
        assert samples_list == ["/samples/c0", "/samples/c1", "/samples/d0"]
        assert expected_classes == [0, 0, 1]
        with Path(output_file).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sample",
                    "prediction",
                    "expected_class",
                    "prob_class0",
                    "prob_class1",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "sample": "c0",
                    "prediction": 0,
                    "expected_class": 0,
                    "prob_class0": 0.9,
                    "prob_class1": 0.1,
                }
            )
            # c1 skipped (unreadable) — only two scored rows, like MethylClassifier realignment
            writer.writerow(
                {
                    "sample": "d0",
                    "prediction": 1,
                    "expected_class": 1,
                    "prob_class0": 0.2,
                    "prob_class1": 0.8,
                }
            )

    monkeypatch.setattr(classifier_cli_main, "classify_samples_from_list", fake_classify)

    metrics = run_prediction(config)

    assert metrics["n_samples"] == 2
    assert metrics["accuracy"] == 1.0
    assert metrics["sensitivity"] == 1.0
    assert metrics["specificity"] == 1.0
    assert metrics["balanced_accuracy"] == 1.0
    assert Path(output_dir / "validation_metrics.json").exists()
    report_path = output_dir / "prediction_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("mode") == "labeled"
    assert report["comparison_label"] == "test_comp"
    assert report["controls"]["label"] == "healthy"
    assert report["diseases"]["label"] == "cancer"
    ctrl_groups = report["controls"]["groups"]
    assert len(ctrl_groups) == 1 and ctrl_groups[0]["label"] == "all"
    assert len(ctrl_groups[0]["samples"]) == 1
    dis_groups = report["diseases"]["groups"]
    assert len(dis_groups[0]["samples"]) == 1
    assert dis_groups[0]["samples"][0]["prob_class1"] == 0.8


def test_run_prediction_blind_mode_writes_report_without_validation_metrics(
    monkeypatch, tmp_path
):
    """Blind cohort: no expected_class, no validation_metrics.json, mode=blind + probabilities."""
    output_dir = tmp_path / "predictor_blind"
    classifier_cli_main = importlib.import_module("methyl_classifier.cli.main")
    config = PredictorConfig(
        model_path=str(tmp_path / "classifier.pkl"),
        output_dir=str(output_dir),
        test_blind_paths=["/blind/s1", "/blind/s2"],
        report_blind={
            "label": "incoming",
            "groups": [{"label": "batch_a", "sample_paths": ["x.csv"]}],
        },
        sample_lineage=[
            {"absolute_path": "/blind/s1", "side": "blind", "group_label": "batch_a"},
            {"absolute_path": "/blind/s2", "side": "blind", "group_label": "batch_a"},
        ],
    )

    monkeypatch.setattr(
        "methyl_classifier.core.classifier.MethylClassifier",
        _DummyClassifier,
    )

    def fake_classify(*, classifier, samples_list, output_file, expected_classes, **_kwargs):
        assert samples_list == ["/blind/s1", "/blind/s2"]
        assert expected_classes is None
        with Path(output_file).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sample",
                    "prediction",
                    "predicted_class",
                    "prob_class0",
                    "prob_class1",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "sample": "s1",
                    "prediction": 0,
                    "predicted_class": "control",
                    "prob_class0": 0.7,
                    "prob_class1": 0.3,
                }
            )
            writer.writerow(
                {
                    "sample": "s2",
                    "prediction": 1,
                    "predicted_class": "disease",
                    "prob_class0": 0.4,
                    "prob_class1": 0.6,
                }
            )

    monkeypatch.setattr(classifier_cli_main, "classify_samples_from_list", fake_classify)

    result = run_prediction(config)

    assert not Path(output_dir / "validation_metrics.json").exists()
    assert result.get("n_samples") == 2
    report_path = output_dir / "prediction_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "blind"
    assert report["validation_metrics"] is None
    assert "blind_summary" in report
    assert report["blind_summary"]["n_samples"] == 2
    assert report["blind_summary"]["predicted_counts_by_class"]["control"] == 1
    samples = report["blind"]["groups"][0]["samples"]
    assert len(samples) == 2
    assert samples[0]["probabilities"]["control"] == 0.7
    assert samples[0]["predicted_subgroup"] == "control"


def test_predictor_config_rejects_blind_with_nested_controls():
    with pytest.raises(ValueError, match="blind"):
        PredictorConfig(
            model_path="/m.pkl",
            output_dir="/out",
            controls={"label": "c", "groups": [{"label": "a", "sample_paths": []}]},
            blind={"groups": [{"label": "b", "sample_paths": []}]},
        )


def test_predictor_config_nested_controls_diseases_expands(tmp_path):
    """Standalone JSON style: controls/diseases nested blocks fill flat paths after expand helper."""
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "s1").mkdir()
    (samples / "s2").mkdir()
    config = PredictorConfig(
        model_path=str(tmp_path / "m.pkl"),
        output_dir=str(tmp_path / "out"),
        samples_base_path=str(samples),
        controls={
            "label": "c",
            "groups": [{"label": "g1", "sample_paths": [str(samples / "s1")]}],
        },
        diseases={
            "label": "d",
            "groups": [{"label": "t1", "sample_paths": [str(samples / "s2")]}],
        },
    )
    _expand_nested_labeled_paths(config)
    assert config.test_control_paths == [str((samples / "s1").resolve())]
    assert config.test_disease_paths == [str((samples / "s2").resolve())]
    assert config.report_controls is not None
    assert config.sample_lineage[0]["group_label"] == "g1"
