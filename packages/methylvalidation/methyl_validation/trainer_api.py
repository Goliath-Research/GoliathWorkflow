"""
Backend training API boundary for ``methyl-validation --model``.

This module isolates backend-specific step construction so orchestration can
stay in MethylValidation now and be extracted to a dedicated trainer package
later with minimal CLI/workflow changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

StepFn = Callable[[], tuple[int, str, str]]
TrainerStep = Tuple[str, StepFn]


def build_model_backend_steps(
    *,
    project_json: Path,
    predictor_output_dir: Optional[Path],
    config: Any,
    per_cancer_group: bool,
    run_classifier_fn: Callable[[Path, bool], tuple[int, str, str]],
    run_predictor_fn: Callable[[Path, Optional[Path]], tuple[int, str, str]],
) -> List[TrainerStep]:
    backend = (config.model_backend if config is not None else "ecdf").strip().lower()
    if backend == "tabular_sklearn":
        model_dir = predictor_output_dir.parent / "classifiers" if predictor_output_dir is not None else project_json.parent / "classifiers"

        def _run_tabular_bundle() -> tuple[int, str, str]:
            try:
                from .model_bundle import build_model_feature_bundle

                bundle_dir = (
                    Path(config.model_bundle_dir)
                    if config is not None and config.model_bundle_dir
                    else (project_json.parent / "model_bundle")
                )
                build_model_feature_bundle(
                    project_json=project_json,
                    output_dir=bundle_dir,
                    weight_column=(config.model_weight_column if config is not None else "weight"),
                    extra_metadata={"model_backend": "tabular_sklearn"},
                )
                return 0, f"Bundle written to {bundle_dir}", ""
            except Exception as e:
                return 1, "", str(e)

        def _run_tabular_train() -> tuple[int, str, str]:
            try:
                from .tabular_backend import train_tabular_model

                bundle_dir = (
                    Path(config.model_bundle_dir)
                    if config is not None and config.model_bundle_dir
                    else (project_json.parent / "model_bundle")
                )
                model_path = train_tabular_model(
                    project_json=project_json,
                    bundle_h5=bundle_dir / "model_feature_bundle.h5",
                    output_dir=model_dir,
                    model_type=(config.tabular_model_type if config is not None else "random_forest"),
                    max_dmps=(config.tabular_max_dmps if config is not None else 5000),
                    covariates_path=(config.covariates_path if config is not None else None),
                    covariate_id_column=(config.covariate_id_column if config is not None else "sample_id"),
                    covariates_strict_join=(config.covariates_strict_join if config is not None else False),
                    covariate_numeric_columns=(config.covariate_numeric_columns if config is not None else None),
                    covariate_categorical_columns=(config.covariate_categorical_columns if config is not None else None),
                    covariate_missing_numeric_strategy=(config.covariate_missing_numeric_strategy if config is not None else "mean"),
                    covariate_standardize_numeric=(config.covariate_standardize_numeric if config is not None else True),
                )
                return 0, f"Tabular model trained: {model_path}", ""
            except Exception as e:
                return 1, "", str(e)

        def _run_tabular_predict() -> tuple[int, str, str]:
            try:
                from .tabular_backend import predict_tabular_model_from_project

                metrics = predict_tabular_model_from_project(
                    project_json=project_json,
                    model_dir=model_dir,
                    output_dir=predictor_output_dir or (project_json.parent / "predictors"),
                    covariates_path=(config.covariates_path if config is not None else None),
                    covariate_id_column=(config.covariate_id_column if config is not None else "sample_id"),
                    covariates_strict_join=(config.covariates_strict_join if config is not None else False),
                )
                return 0, json.dumps(metrics), ""
            except Exception as e:
                return 1, "", str(e)

        return [
            ("model-bundle", _run_tabular_bundle),
            ("tabular-train", _run_tabular_train),
            ("tabular-predictor", _run_tabular_predict),
        ]

    if backend == "generative_hybrid":
        model_dir = predictor_output_dir.parent / "classifiers" if predictor_output_dir is not None else project_json.parent / "classifiers"

        def _run_generative_bundle() -> tuple[int, str, str]:
            try:
                from .model_bundle import build_model_feature_bundle

                bundle_dir = (
                    Path(config.model_bundle_dir)
                    if config is not None and config.model_bundle_dir
                    else (project_json.parent / "model_bundle")
                )
                build_model_feature_bundle(
                    project_json=project_json,
                    output_dir=bundle_dir,
                    weight_column=(config.model_weight_column if config is not None else "weight"),
                    extra_metadata={"model_backend": "generative_hybrid"},
                )
                return 0, f"Bundle written to {bundle_dir}", ""
            except Exception as e:
                return 1, "", str(e)

        def _run_generative_train() -> tuple[int, str, str]:
            try:
                from .generative_backend import train_generative_model

                bundle_dir = (
                    Path(config.model_bundle_dir)
                    if config is not None and config.model_bundle_dir
                    else (project_json.parent / "model_bundle")
                )
                model_path = train_generative_model(
                    project_json=project_json,
                    bundle_h5=bundle_dir / "model_feature_bundle.h5",
                    output_dir=model_dir,
                    max_dmps=(config.tabular_max_dmps if config is not None else 5000),
                    latent_dim=(config.generative_latent_dim if config is not None else 16),
                    kl_weight=(config.generative_kl_weight if config is not None else 0.1),
                    density_type=(config.generative_density_type if config is not None else "diag_gaussian"),
                    epochs=(config.generative_epochs if config is not None else 50),
                    batch_size=(config.generative_batch_size if config is not None else 64),
                    random_seed=(config.generative_seed if config is not None else 13),
                    calibrate=(config.generative_calibrate if config is not None else False),
                    covariates_path=(config.covariates_path if config is not None else None),
                    covariate_id_column=(config.covariate_id_column if config is not None else "sample_id"),
                    covariates_strict_join=(config.generative_covariates_strict if config is not None else True),
                    covariate_numeric_columns=(config.covariate_numeric_columns if config is not None else None),
                    covariate_categorical_columns=(config.covariate_categorical_columns if config is not None else None),
                    covariate_missing_numeric_strategy=(config.covariate_missing_numeric_strategy if config is not None else "mean"),
                    covariate_standardize_numeric=(config.covariate_standardize_numeric if config is not None else True),
                )
                return 0, f"Generative model trained: {model_path}", ""
            except Exception as e:
                return 1, "", str(e)

        def _run_generative_predict() -> tuple[int, str, str]:
            try:
                from .generative_backend import predict_generative_model_from_project

                metrics = predict_generative_model_from_project(
                    project_json=project_json,
                    model_dir=model_dir,
                    output_dir=predictor_output_dir or (project_json.parent / "predictors"),
                    covariates_path=(config.covariates_path if config is not None else None),
                    covariate_id_column=(config.covariate_id_column if config is not None else "sample_id"),
                    covariates_strict_join=(config.generative_covariates_strict if config is not None else True),
                )
                return 0, json.dumps(metrics), ""
            except Exception as e:
                return 1, "", str(e)

        return [
            ("model-bundle", _run_generative_bundle),
            ("generative-train", _run_generative_train),
            ("generative-predictor", _run_generative_predict),
        ]

    return [
        ("methyl-classifier", lambda: run_classifier_fn(project_json, per_cancer_group)),
        ("methyl-predictor", lambda: run_predictor_fn(project_json, predictor_output_dir)),
    ]
