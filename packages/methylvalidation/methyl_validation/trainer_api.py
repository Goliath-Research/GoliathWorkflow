"""
Backend training API boundary for ``methyl-validation --model``.

This module isolates backend-specific step construction so orchestration can
stay in MethylValidation now and be extracted to a dedicated trainer package
later with minimal CLI/workflow changes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

StepFn = Callable[[], tuple[int, str, str]]
TrainerStep = Tuple[str, StepFn]


def _write_ecdf_training_metrics(project_json: Path, classifier_output_dir: Path) -> tuple[bool, str]:
    """
    Evaluate the ECDF classifier on training cohorts and persist training_metrics.json.

    Returns (success, message_or_path).
    """
    try:
        from methyl_predictor.core.predictor import run_prediction
        from methyl_predictor.models.config import PredictorConfig
        from methyl_predictor.project_resolver import resolve_predictor_config
        from methyl_utils import load_project
    except Exception as e:
        return False, f"ECDF training metrics unavailable (imports): {e}"

    try:
        project = load_project(project_json)
        resolved_groups = project.get_resolved_groups()
        if not resolved_groups:
            return False, "ECDF training metrics unavailable: no resolved training groups."

        base_predictor = resolve_predictor_config(project_json)
        test_group_paths = [
            {
                "label": str(label),
                "class_index": int(idx),
                "paths": [str(p) for p in (paths or [])],
            }
            for idx, (label, paths) in enumerate(resolved_groups)
            if paths
        ]
        if not test_group_paths:
            return False, "ECDF training metrics unavailable: resolved groups had no sample paths."

        classifier_output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=str(classifier_output_dir),
            prefix=".ecdf-training-eval-",
        ) as tmp_out:
            cfg = PredictorConfig(
                model_path=base_predictor.model_path,
                model_dir=base_predictor.model_dir,
                output_dir=tmp_out,
                test_group_paths=test_group_paths,
                test_control_paths=[],
                test_disease_paths=[],
                samples_base_path=base_predictor.samples_base_path,
                path_remap=base_predictor.path_remap,
                debug=bool(base_predictor.debug),
                classifier_step_snapshot=base_predictor.classifier_step_snapshot,
                panel=base_predictor.panel,
                decision_enabled=bool(base_predictor.decision_enabled),
                decision_min_margin=float(base_predictor.decision_min_margin),
                decision_min_confidence=float(base_predictor.decision_min_confidence),
            )
            metrics = run_prediction(cfg)

        if not isinstance(metrics, dict) or not metrics:
            return False, "ECDF training metrics unavailable: predictor returned empty metrics."

        payload = dict(metrics)
        payload["metrics_source"] = "ecdf_train"
        payload["evaluation_split"] = "training"
        payload["model_backend"] = "ecdf"
        n_train_samples = 0
        for g in test_group_paths:
            paths = g.get("paths")
            if isinstance(paths, list):
                n_train_samples += len(paths)
        payload["n_train_samples"] = int(n_train_samples)
        payload["n_train_groups"] = int(len(test_group_paths))
        out_path = classifier_output_dir / "training_metrics.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return True, str(out_path)
    except Exception as e:
        return False, f"ECDF training metrics unavailable: {e}"


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
    feature_mode = (config.feature_mode if config is not None else "raw_dmp").strip().lower()
    feature_family_set = (config.feature_family_set if config is not None else "dmp").strip().lower()
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
                    weight_column=(config.model_weight_column if config is not None else "effect_size"),
                    feature_family_set=feature_family_set,
                    require_mapper_annotations=(feature_family_set != "dmp"),
                    extra_metadata={
                        "model_backend": "tabular_sklearn",
                        "feature_mode": (config.feature_mode if config is not None else "raw_dmp"),
                        "feature_family_set": (config.feature_family_set if config is not None else "dmp"),
                    },
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
                    bundle_dir=bundle_dir,
                    output_dir=model_dir,
                    model_type=(config.tabular_model_type if config is not None else "random_forest"),
                    tabular_methods=(config.tabular_methods if config is not None else None),
                    tabular_method_selection_metric=(
                        config.tabular_method_selection_metric if config is not None else "balanced_accuracy"
                    ),
                    tabular_method_selection_stat=(
                        config.tabular_method_selection_stat if config is not None else "mean"
                    ),
                    max_dmps=(config.tabular_max_dmps if config is not None else 0),
                    covariates_path=(config.covariates_path if config is not None else None),
                    covariate_id_column=(config.covariate_id_column if config is not None else "sample_id"),
                    covariates_strict_join=(config.covariates_strict_join if config is not None else False),
                    covariate_numeric_columns=(config.covariate_numeric_columns if config is not None else None),
                    covariate_ordinal_columns=(config.covariate_ordinal_columns if config is not None else None),
                    covariate_ordinal_maps=(config.covariate_ordinal_maps if config is not None else None),
                    covariate_ordinal_unknown_value=(config.covariate_ordinal_unknown_value if config is not None else 0.0),
                    covariate_categorical_columns=(config.covariate_categorical_columns if config is not None else None),
                    covariate_missing_numeric_strategy=(config.covariate_missing_numeric_strategy if config is not None else "mean"),
                    covariate_standardize_numeric=(config.covariate_standardize_numeric if config is not None else True),
                    feature_mode=(config.feature_mode if config is not None else "raw_dmp"),
                    observed_feature_quantiles=(config.observed_feature_quantiles if config is not None else None),
                    observed_feature_min_coverage=(config.observed_feature_min_coverage if config is not None else 1),
                    observed_feature_min_obs_fraction=(
                        config.observed_feature_min_obs_fraction if config is not None else 0.0
                    ),
                    observed_feature_include_dmp=(
                        config.observed_feature_include_dmp if config is not None else True
                    ),
                    observed_feature_include_chromosome=(
                        config.observed_feature_include_chromosome if config is not None else True
                    ),
                    observed_feature_include_dmr=(
                        config.observed_feature_include_dmr if config is not None else True
                    ),
                    observed_feature_include_gene=(
                        config.observed_feature_include_gene if config is not None else True
                    ),
                    observed_feature_dmr_window_bp=(
                        config.observed_feature_dmr_window_bp if config is not None else 100000
                    ),
                    observed_feature_max_dmrs=(
                        config.observed_feature_max_dmrs if config is not None else 32
                    ),
                    observed_feature_max_genes=(
                        config.observed_feature_max_genes if config is not None else 32
                    ),
                    feature_family_set=(config.feature_family_set if config is not None else "dmp"),
                    gene_feature_loading=(config.gene_feature_loading if config is not None else "frozen"),
                    observed_hist_eps=(config.observed_hist_eps if config is not None else 1e-6),
                    observed_hist_alpha=(config.observed_hist_alpha if config is not None else 0.5),
                    observed_hist_evidence_clip_cap=(
                        config.observed_hist_evidence_clip_cap if config is not None else 5.0
                    ),
                    observed_hist_tail_agreement_threshold=(
                        config.observed_hist_tail_agreement_threshold if config is not None else 0.10
                    ),
                    gene_scored_min_support_n=(
                        config.gene_scored_min_support_n if config is not None else 2
                    ),
                    gene_scored_use_region_weight=(
                        config.gene_scored_use_region_weight if config is not None else True
                    ),
                    gene_scored_gene_weight=(
                        config.gene_scored_gene_weight if config is not None else "importance_x_sqrt_support"
                    ),
                    region_directional_region_types=(
                        config.region_directional_region_types if config is not None else None
                    ),
                    region_directional_min_loci=(
                        config.region_directional_min_loci if config is not None else 1
                    ),
                    observed_feature_quality_columns=(
                        config.observed_feature_quality_columns if config is not None else None
                    ),
                    save_train_dataset=(
                        bool(config.tabular_save_train_dataset)
                        if config is not None
                        else False
                    ),
                    reuse_train_dataset=(
                        bool(config.tabular_reuse_train_dataset)
                        if config is not None
                        else True
                    ),
                    train_dataset_path=(
                        config.tabular_train_dataset_path
                        if config is not None
                        else None
                    ),
                    save_test_dataset=(
                        bool(config.tabular_save_test_dataset)
                        if config is not None
                        else True
                    ),
                    test_dataset_path=(
                        config.tabular_test_dataset_path
                        if config is not None
                        else None
                    ),
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
                    observed_feature_min_obs_fraction=(
                        config.observed_feature_min_obs_fraction if config is not None else 0.0
                    ),
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
                    weight_column=(config.model_weight_column if config is not None else "effect_size"),
                    feature_family_set=feature_family_set,
                    require_mapper_annotations=(feature_family_set != "dmp"),
                    extra_metadata={
                        "model_backend": "generative_hybrid",
                        "feature_mode": (config.feature_mode if config is not None else "raw_dmp"),
                        "feature_family_set": (config.feature_family_set if config is not None else "dmp"),
                    },
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
                    max_dmps=(config.tabular_max_dmps if config is not None else 0),
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
                    covariate_ordinal_columns=(config.covariate_ordinal_columns if config is not None else None),
                    covariate_ordinal_maps=(config.covariate_ordinal_maps if config is not None else None),
                    covariate_ordinal_unknown_value=(config.covariate_ordinal_unknown_value if config is not None else 0.0),
                    covariate_categorical_columns=(config.covariate_categorical_columns if config is not None else None),
                    covariate_missing_numeric_strategy=(config.covariate_missing_numeric_strategy if config is not None else "mean"),
                    covariate_standardize_numeric=(config.covariate_standardize_numeric if config is not None else True),
                    feature_mode=(config.feature_mode if config is not None else "raw_dmp"),
                    observed_feature_quantiles=(config.observed_feature_quantiles if config is not None else None),
                    observed_feature_min_coverage=(config.observed_feature_min_coverage if config is not None else 1),
                    observed_feature_min_obs_fraction=(
                        config.observed_feature_min_obs_fraction if config is not None else 0.0
                    ),
                    observed_feature_include_dmp=(
                        config.observed_feature_include_dmp if config is not None else True
                    ),
                    observed_feature_include_chromosome=(
                        config.observed_feature_include_chromosome if config is not None else True
                    ),
                    observed_feature_include_dmr=(
                        config.observed_feature_include_dmr if config is not None else True
                    ),
                    observed_feature_include_gene=(
                        config.observed_feature_include_gene if config is not None else True
                    ),
                    observed_feature_dmr_window_bp=(
                        config.observed_feature_dmr_window_bp if config is not None else 100000
                    ),
                    observed_feature_max_dmrs=(
                        config.observed_feature_max_dmrs if config is not None else 32
                    ),
                    observed_feature_max_genes=(
                        config.observed_feature_max_genes if config is not None else 32
                    ),
                    feature_family_set=(config.feature_family_set if config is not None else "dmp"),
                    gene_feature_loading=(config.gene_feature_loading if config is not None else "frozen"),
                    observed_hist_eps=(config.observed_hist_eps if config is not None else 1e-6),
                    observed_hist_alpha=(config.observed_hist_alpha if config is not None else 0.5),
                    observed_hist_evidence_clip_cap=(
                        config.observed_hist_evidence_clip_cap if config is not None else 5.0
                    ),
                    observed_hist_tail_agreement_threshold=(
                        config.observed_hist_tail_agreement_threshold if config is not None else 0.10
                    ),
                    gene_scored_min_support_n=(
                        config.gene_scored_min_support_n if config is not None else 2
                    ),
                    gene_scored_use_region_weight=(
                        config.gene_scored_use_region_weight if config is not None else True
                    ),
                    gene_scored_gene_weight=(
                        config.gene_scored_gene_weight if config is not None else "importance_x_sqrt_support"
                    ),
                    region_directional_region_types=(
                        config.region_directional_region_types if config is not None else None
                    ),
                    region_directional_min_loci=(
                        config.region_directional_min_loci if config is not None else 1
                    ),
                    observed_feature_quality_columns=(
                        config.observed_feature_quality_columns if config is not None else None
                    ),
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
                    observed_feature_min_obs_fraction=(
                        config.observed_feature_min_obs_fraction if config is not None else 0.0
                    ),
                )
                return 0, json.dumps(metrics), ""
            except Exception as e:
                return 1, "", str(e)

        return [
            ("model-bundle", _run_generative_bundle),
            ("generative-train", _run_generative_train),
            ("generative-predictor", _run_generative_predict),
        ]

    ecdf_aggregated_auto = feature_mode == "observed_hybrid" and feature_family_set != "dmp"
    ecdf_aggregated_enabled = (
        bool(config.ecdf_aggregated_enabled)
        if config is not None and config.ecdf_aggregated_enabled is not None
        else ecdf_aggregated_auto
    )
    if backend == "ecdf" and ecdf_aggregated_enabled:
        model_dir = (
            predictor_output_dir.parent / "classifiers"
            if predictor_output_dir is not None
            else project_json.parent / "classifiers"
        )

        def _run_ecdf_aggregated_bundle() -> tuple[int, str, str]:
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
                    weight_column=(config.model_weight_column if config is not None else "effect_size"),
                    feature_family_set=feature_family_set,
                    require_mapper_annotations=(feature_family_set != "dmp"),
                    extra_metadata={
                        "model_backend": "ecdf",
                        "classifier_type": "ecdf_aggregated_one_vs_rest",
                        "feature_mode": feature_mode,
                        "feature_family_set": feature_family_set,
                    },
                )
                return 0, f"Bundle written to {bundle_dir}", ""
            except Exception as e:
                return 1, "", str(e)

        def _run_ecdf_aggregated_train() -> tuple[int, str, str]:
            try:
                from .ecdf_aggregated_backend import train_ecdf_aggregated_ovr_model

                bundle_dir = (
                    Path(config.model_bundle_dir)
                    if config is not None and config.model_bundle_dir
                    else (project_json.parent / "model_bundle")
                )
                model_path = train_ecdf_aggregated_ovr_model(
                    project_json=project_json,
                    bundle_h5=bundle_dir / "model_feature_bundle.h5",
                    output_dir=model_dir,
                    feature_family_set=feature_family_set,
                    observed_feature_min_coverage=(
                        config.observed_feature_min_coverage if config is not None else 1
                    ),
                    observed_feature_quality_columns=(
                        config.observed_feature_quality_columns if config is not None else None
                    ),
                    observed_hist_eps=(config.observed_hist_eps if config is not None else 1e-6),
                    observed_hist_alpha=(config.observed_hist_alpha if config is not None else 0.5),
                    observed_hist_evidence_clip_cap=(
                        config.observed_hist_evidence_clip_cap if config is not None else 5.0
                    ),
                    observed_hist_tail_agreement_threshold=(
                        config.observed_hist_tail_agreement_threshold if config is not None else 0.10
                    ),
                    n_bins=(config.ecdf_aggregated_n_bins if config is not None else 100),
                    temperature=1.0,
                )
                return 0, f"Aggregated ECDF model trained: {model_path}", ""
            except Exception as e:
                return 1, "", str(e)

        def _run_ecdf_aggregated_predict() -> tuple[int, str, str]:
            try:
                from .ecdf_aggregated_backend import predict_ecdf_aggregated_ovr_from_project

                model_path = model_dir / "ecdf_aggregated_ovr.pkl"
                metrics = predict_ecdf_aggregated_ovr_from_project(
                    project_json=project_json,
                    model_path=model_path,
                    output_dir=(predictor_output_dir or (project_json.parent / "predictors")),
                )
                return 0, json.dumps(metrics), ""
            except Exception as e:
                return 1, "", str(e)

        def _skip_ecdf_second_stage_aggregated() -> tuple[int, str, str]:
            return 0, "ECDF second-stage scorer skipped for aggregated ECDF OvR mode.", ""

        return [
            ("model-bundle", _run_ecdf_aggregated_bundle),
            ("ecdf-aggregated-train", _run_ecdf_aggregated_train),
            ("ecdf-aggregated-predictor", _run_ecdf_aggregated_predict),
            ("ecdf-second-stage", _skip_ecdf_second_stage_aggregated),
        ]

    def _run_ecdf_second_stage() -> tuple[int, str, str]:
        classifier_output_dir = (
            predictor_output_dir.parent / "classifiers"
            if predictor_output_dir is not None
            else project_json.parent / "classifiers"
        )
        tm_ok, tm_msg = _write_ecdf_training_metrics(project_json, classifier_output_dir)
        try:
            if config is None or not bool(config.ecdf_second_stage_enabled):
                if tm_ok:
                    return 0, f"ECDF second-stage scorer disabled. Training metrics saved: {tm_msg}", ""
                return 0, f"ECDF second-stage scorer disabled. {tm_msg}", ""
            from .ecdf_second_stage import train_and_apply_ecdf_second_stage

            out = train_and_apply_ecdf_second_stage(
                project_json=project_json,
                predictor_output_dir=(predictor_output_dir or (project_json.parent / "predictors")),
                classifier_output_dir=(predictor_output_dir.parent / "classifiers" if predictor_output_dir is not None else project_json.parent / "classifiers"),
                max_dmps=(config.tabular_max_dmps if config is not None else 0),
                quantiles=(config.observed_feature_quantiles if config is not None else None),
                min_coverage=(config.observed_feature_min_coverage if config is not None else 1),
                include_dmp_features=(config.observed_feature_include_dmp if config is not None else True),
                include_chromosome_features=(
                    config.observed_feature_include_chromosome if config is not None else True
                ),
                include_dmr_features=(config.observed_feature_include_dmr if config is not None else True),
                include_gene_features=(config.observed_feature_include_gene if config is not None else True),
                dmr_window_bp=(config.observed_feature_dmr_window_bp if config is not None else 100000),
                max_dmr_features=(config.observed_feature_max_dmrs if config is not None else 32),
                max_gene_features=(config.observed_feature_max_genes if config is not None else 32),
                hist_eps=(config.observed_hist_eps if config is not None else 1e-6),
                hist_alpha=(config.observed_hist_alpha if config is not None else 0.5),
                hist_evidence_clip_cap=(
                    config.observed_hist_evidence_clip_cap if config is not None else 5.0
                ),
                hist_tail_agreement_threshold=(
                    config.observed_hist_tail_agreement_threshold if config is not None else 0.10
                ),
            )
            if isinstance(out, dict):
                out["training_metrics_saved"] = bool(tm_ok)
                out["training_metrics_path"] = tm_msg if tm_ok else None
                out["training_metrics_note"] = None if tm_ok else tm_msg
            return 0, json.dumps(out), ""
        except Exception as e:
            # Optional refinement must not fail the primary ECDF build.
            if not tm_ok:
                return 0, "", f"ECDF second-stage skipped: {e}. {tm_msg}"
            return 0, "", f"ECDF second-stage skipped: {e}. Training metrics saved: {tm_msg}"

    return [
        ("methyl-classifier", lambda: run_classifier_fn(project_json, per_cancer_group)),
        ("methyl-predictor", lambda: run_predictor_fn(project_json, predictor_output_dir)),
        ("ecdf-second-stage", _run_ecdf_second_stage),
    ]
