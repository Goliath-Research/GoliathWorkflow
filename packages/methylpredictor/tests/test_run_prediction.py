"""Regression tests for predictor metrics and path normalization."""

import csv
import importlib
from pathlib import Path

from methyl_predictor.models.config import PredictorConfig
from methyl_predictor.core.predictor import run_prediction


class _DummyClassifier:
    def __init__(self, *_args, **_kwargs):
        self.n_classes = 2
        self.class_names = ["control", "disease"]
        self.is_multi_chromosome = False
        self.classifier = self

    def get_feature_info(self):
        return {"positions": [10, 20]}


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
                fieldnames=["sample", "prediction", "expected_class"],
            )
            writer.writeheader()
            writer.writerow(
                {"sample": "control-loaded", "prediction": 0, "expected_class": 0}
            )
            writer.writerow(
                {"sample": "disease-loaded", "prediction": 1, "expected_class": 1}
            )

    monkeypatch.setattr(classifier_cli_main, "classify_samples_from_list", fake_classify)

    metrics = run_prediction(config)

    assert metrics["n_samples"] == 2
    assert metrics["accuracy"] == 1.0
    assert metrics["sensitivity"] == 1.0
    assert metrics["specificity"] == 1.0
    assert metrics["balanced_accuracy"] == 1.0
    assert Path(output_dir / "validation_metrics.json").exists()
