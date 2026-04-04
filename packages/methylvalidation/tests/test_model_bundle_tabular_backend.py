from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np
import pandas as pd

from methyl_validation import model_bundle, tabular_backend


class _StubProject:
    def __init__(self, detection_dir: Path):
        self.project_name = "stubproj"
        self._det = detection_dir

    def get_comparisons(self):
        return [
            SimpleNamespace(
                control_group="healthy",
                disease_group="pca1",
                comparison_label="healthy_vs_pca1",
            )
        ]

    def get_detection_output_dir(self, control_group: str, disease_group: str) -> str:
        assert control_group == "healthy"
        assert disease_group == "pca1"
        return str(self._det)

    def get_derived_paths(self):
        return SimpleNamespace(detection_dir=str(self._det))

    def get_resolved_groups(self):
        return [
            ("healthy", ["/tmp/S1", "/tmp/S2"]),
            ("pca1", ["/tmp/S3", "/tmp/S4"]),
        ]


def test_build_model_feature_bundle_and_load(tmp_path: Path, monkeypatch):
    det = tmp_path / "detections" / "healthy" / "pca1"
    det.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "chromosome": ["1", "1", "1"],
            "position": [100, 120, 200],
            "context": ["CG", "CG", "CHG"],
            "effect_size": [0.7, 0.4, 0.9],
            "weight": [0.8, 0.3, 1.0],
        }
    )
    dmp_csv = det / "dmps-1-classifier.csv"
    df.to_csv(dmp_csv, index=False)

    monkeypatch.setattr(model_bundle, "load_project", lambda _p: _StubProject(det))

    manifest_path = model_bundle.build_model_feature_bundle(
        project_json=tmp_path / "project.json",
        output_dir=tmp_path / "bundle",
    )
    assert manifest_path.is_file()
    assert (tmp_path / "bundle" / "detection_model_bundle.json").is_file()

    out_df = model_bundle.load_bundle_dmp_index(tmp_path / "bundle" / "model_feature_bundle.h5")
    assert len(out_df) == 3
    assert set(out_df.columns) >= {"chromosome", "position", "context", "weight", "comparison_label"}


def test_tabular_backend_train_and_predict(tmp_path: Path, monkeypatch):
    det = tmp_path / "detections" / "healthy" / "pca1"
    det.mkdir(parents=True)
    pd.DataFrame(
        {
            "chromosome": ["1", "1", "1"],
            "position": [100, 120, 200],
            "context": ["CG", "CG", "CG"],
            "effect_size": [0.7, 0.4, 0.9],
            "weight": [0.8, 0.3, 1.0],
        }
    ).to_csv(det / "dmps-1-classifier.csv", index=False)

    monkeypatch.setattr(model_bundle, "load_project", lambda _p: _StubProject(det))
    bundle_dir = tmp_path / "bundle"
    model_bundle.build_model_feature_bundle(tmp_path / "project.json", bundle_dir)

    monkeypatch.setattr(tabular_backend, "load_project", lambda _p: _StubProject(det))

    def _fake_extract(sample_paths, reference_positions, chromosome, min_coverage=1):
        positions = np.asarray(reference_positions["CG"], dtype=np.uint32)
        n = len(sample_paths)
        X = np.zeros((n, len(positions)), dtype=np.float32)
        for i, p in enumerate(sample_paths):
            # Control-like samples low methylation, disease-like high methylation.
            base = 0.1 if Path(str(p)).name in {"S1", "S2"} else 0.9
            X[i, :] = base
        ctx = np.asarray(["CG"] * len(positions), dtype=object)
        return X, positions, ctx, {"CG": np.arange(len(positions), dtype=np.uint32)}

    monkeypatch.setattr(
        tabular_backend.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract,
    )

    model_dir = tmp_path / "model"
    tabular_backend.train_tabular_model(
        project_json=tmp_path / "project.json",
        bundle_h5=bundle_dir / "model_feature_bundle.h5",
        output_dir=model_dir,
        model_type="random_forest",
        max_dmps=100,
    )
    assert (model_dir / "tabular-model.joblib").is_file()
    assert (model_dir / "tabular-model-metadata.json").is_file()

    predictor_cfg = SimpleNamespace(
        test_control_paths=["/tmp/S1", "/tmp/S2"],
        test_disease_paths=["/tmp/S3", "/tmp/S4"],
    )
    monkeypatch.setattr(tabular_backend, "resolve_predictor_config", lambda _p: predictor_cfg)
    metrics = tabular_backend.predict_tabular_model_from_project(
        project_json=tmp_path / "project.json",
        model_dir=model_dir,
        output_dir=tmp_path / "predict",
    )
    assert "balanced_accuracy" in metrics
    assert (tmp_path / "predict" / "predictions.csv").is_file()


def test_tabular_covariate_preprocessor_categorical(tmp_path: Path, monkeypatch):
    det = tmp_path / "detections" / "healthy" / "pca1"
    det.mkdir(parents=True)
    pd.DataFrame(
        {
            "chromosome": ["1", "1"],
            "position": [100, 120],
            "context": ["CG", "CG"],
            "effect_size": [0.7, 0.4],
            "weight": [0.8, 0.3],
        }
    ).to_csv(det / "dmps-1-classifier.csv", index=False)

    monkeypatch.setattr(model_bundle, "load_project", lambda _p: _StubProject(det))
    bundle_dir = tmp_path / "bundle"
    model_bundle.build_model_feature_bundle(tmp_path / "project.json", bundle_dir)
    monkeypatch.setattr(tabular_backend, "load_project", lambda _p: _StubProject(det))

    def _fake_extract(sample_paths, reference_positions, chromosome, min_coverage=1):
        positions = np.asarray(reference_positions["CG"], dtype=np.uint32)
        X = np.full((len(sample_paths), len(positions)), 0.5, dtype=np.float32)
        ctx = np.asarray(["CG"] * len(positions), dtype=object)
        return X, positions, ctx, {"CG": np.arange(len(positions), dtype=np.uint32)}

    monkeypatch.setattr(tabular_backend.MethylCentroidPair, "extract_methylation_fractions", _fake_extract)

    cov_csv = tmp_path / "cov.csv"
    pd.DataFrame(
        {
            "sample_id": ["S1", "S2", "S3", "S4"],
            "age": [55, 60, 68, 71],
            "ethnicity": ["A", "B", "A", "C"],
        }
    ).to_csv(cov_csv, index=False)

    model_dir = tmp_path / "model"
    tabular_backend.train_tabular_model(
        project_json=tmp_path / "project.json",
        bundle_h5=bundle_dir / "model_feature_bundle.h5",
        output_dir=model_dir,
        model_type="logistic_regression",
        covariates_path=str(cov_csv),
        covariates_strict_join=True,
    )
    assert (model_dir / "covariate-preprocessor.json").is_file()
    with open(model_dir / "tabular-model-metadata.json", encoding="utf-8") as f:
        meta = json.load(f)
    assert bool(meta["covariate_preprocessing"]["used"]) is True


def test_tabular_covariate_preprocessor_ordinal(tmp_path: Path, monkeypatch):
    det = tmp_path / "detections" / "healthy" / "pca1"
    det.mkdir(parents=True)
    pd.DataFrame(
        {
            "chromosome": ["1", "1"],
            "position": [100, 120],
            "context": ["CG", "CG"],
            "effect_size": [0.7, 0.4],
            "weight": [0.8, 0.3],
        }
    ).to_csv(det / "dmps-1-classifier.csv", index=False)

    monkeypatch.setattr(model_bundle, "load_project", lambda _p: _StubProject(det))
    bundle_dir = tmp_path / "bundle"
    model_bundle.build_model_feature_bundle(tmp_path / "project.json", bundle_dir)
    monkeypatch.setattr(tabular_backend, "load_project", lambda _p: _StubProject(det))

    def _fake_extract(sample_paths, reference_positions, chromosome, min_coverage=1):
        positions = np.asarray(reference_positions["CG"], dtype=np.uint32)
        X = np.full((len(sample_paths), len(positions)), 0.5, dtype=np.float32)
        ctx = np.asarray(["CG"] * len(positions), dtype=object)
        return X, positions, ctx, {"CG": np.arange(len(positions), dtype=np.uint32)}

    monkeypatch.setattr(tabular_backend.MethylCentroidPair, "extract_methylation_fractions", _fake_extract)

    cov_train_csv = tmp_path / "cov-train.csv"
    pd.DataFrame(
        {
            "sample_id": ["S1", "S2", "S3", "S4"],
            "age": [55, 60, 68, 71],
            "risk_band": ["low", "medium", "high", "high"],
            "ethnicity": ["A", "B", "A", "C"],
        }
    ).to_csv(cov_train_csv, index=False)

    model_dir = tmp_path / "model"
    tabular_backend.train_tabular_model(
        project_json=tmp_path / "project.json",
        bundle_h5=bundle_dir / "model_feature_bundle.h5",
        output_dir=model_dir,
        model_type="logistic_regression",
        covariates_path=str(cov_train_csv),
        covariates_strict_join=True,
        covariate_numeric_columns=["age"],
        covariate_ordinal_columns=["risk_band"],
        covariate_ordinal_maps={"risk_band": {"low": 1, "medium": 2, "high": 3}},
        covariate_categorical_columns=["ethnicity"],
    )

    with open(model_dir / "covariate-preprocessor.json", encoding="utf-8") as f:
        pre = json.load(f)
    assert pre["ordinal_columns"] == ["risk_band"]
    assert pre["ordinal_maps"]["risk_band"]["high"] == 3.0

    predictor_cfg = SimpleNamespace(
        test_control_paths=["/tmp/S1", "/tmp/S2"],
        test_disease_paths=["/tmp/S3", "/tmp/S4"],
    )
    monkeypatch.setattr(tabular_backend, "resolve_predictor_config", lambda _p: predictor_cfg)

    cov_predict_csv = tmp_path / "cov-predict.csv"
    pd.DataFrame(
        {
            "sample_id": ["S1", "S2", "S3", "S4"],
            "age": [56, 61, 69, 73],
            "risk_band": ["low", "very_high", "high", "medium"],
            "ethnicity": ["A", "B", "A", "C"],
        }
    ).to_csv(cov_predict_csv, index=False)
    metrics = tabular_backend.predict_tabular_model_from_project(
        project_json=tmp_path / "project.json",
        model_dir=model_dir,
        output_dir=tmp_path / "predict",
        covariates_path=str(cov_predict_csv),
        covariates_strict_join=True,
    )
    assert int(metrics["covariate_preprocessing"]["unknown_ordinal_values_mapped"]) >= 1


def test_tabular_resolve_eval_paths_multiclass_falls_back_from_binary_predictor(tmp_path: Path, monkeypatch):
    class _StubProjectMulti:
        def get_resolved_groups(self):
            return [
                ("healthy", ["/tmp/S1", "/tmp/S2"]),
                ("pca1", ["/tmp/S3", "/tmp/S4"]),
                ("pca2", ["/tmp/S5", "/tmp/S6"]),
            ]

    stub = _StubProjectMulti()
    predictor_cfg = SimpleNamespace(
        test_group_paths=None,
        test_control_paths=["/tmp/S1", "/tmp/S2"],
        test_disease_paths=["/tmp/S3", "/tmp/S4"],
    )
    monkeypatch.setattr(tabular_backend, "resolve_predictor_config", lambda _p: predictor_cfg)
    monkeypatch.setattr(tabular_backend, "load_project", lambda _p: stub)
    samples, y_true = tabular_backend._resolve_eval_paths_and_labels(
        project_json=tmp_path / "project.json",
        class_names=["healthy", "pca1", "pca2"],
    )
    assert len(samples) == 6
    assert set(np.unique(y_true).tolist()) == {0, 1, 2}
