from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Tuple

from methyl_validation.cohort_inference import infer_monte_carlo_cohorts_from_project
from methyl_validation.config import BackendProfilesConfig, MonteCarloConfig


LEGACY_BACKEND_KEYS = {
    "model_backend",
    "model_bundle_dir",
    "model_weight_column",
    "tabular_model_type",
    "tabular_methods",
    "tabular_method_selection_metric",
    "tabular_method_selection_stat",
    "tabular_max_dmps",
    "tabular_save_train_dataset",
    "tabular_reuse_train_dataset",
    "tabular_train_dataset_path",
    "tabular_save_test_dataset",
    "tabular_test_dataset_path",
    "feature_mode",
    "feature_family_set",
    "gene_feature_loading",
    "observed_feature_quantiles",
    "observed_feature_min_coverage",
    "observed_feature_min_obs_fraction",
    "observed_feature_include_dmp",
    "observed_feature_include_chromosome",
    "observed_feature_include_dmr",
    "observed_feature_include_gene",
    "observed_feature_dmr_window_bp",
    "observed_feature_max_dmrs",
    "observed_feature_max_genes",
    "observed_hist_eps",
    "observed_hist_alpha",
    "observed_hist_evidence_clip_cap",
    "observed_hist_tail_agreement_threshold",
    "gene_scored_min_support_n",
    "gene_scored_use_region_weight",
    "gene_scored_gene_weight",
    "ecdf_second_stage_enabled",
    "covariates_path",
    "covariate_id_column",
    "covariate_numeric_columns",
    "covariate_ordinal_columns",
    "covariate_ordinal_maps",
    "covariate_ordinal_unknown_value",
    "covariate_categorical_columns",
    "covariate_missing_numeric_strategy",
    "covariate_standardize_numeric",
    "covariates_strict_join",
    "generative_latent_dim",
    "generative_kl_weight",
    "generative_density_type",
    "generative_epochs",
    "generative_batch_size",
    "generative_seed",
    "generative_calibrate",
    "generative_covariates_strict",
}

SHARED_PARAM_KEYS = {
    "model_bundle_dir",
    "model_weight_column",
    "tabular_max_dmps",
    "feature_mode",
    "feature_family_set",
    "gene_feature_loading",
    "observed_feature_quantiles",
    "observed_feature_min_coverage",
    "observed_feature_min_obs_fraction",
    "observed_feature_include_dmp",
    "observed_feature_include_chromosome",
    "observed_feature_include_dmr",
    "observed_feature_include_gene",
    "observed_feature_dmr_window_bp",
    "observed_feature_max_dmrs",
    "observed_feature_max_genes",
    "observed_hist_eps",
    "observed_hist_alpha",
    "observed_hist_evidence_clip_cap",
    "observed_hist_tail_agreement_threshold",
    "gene_scored_min_support_n",
    "gene_scored_use_region_weight",
    "gene_scored_gene_weight",
    "covariates_path",
    "covariate_id_column",
    "covariate_numeric_columns",
    "covariate_ordinal_columns",
    "covariate_ordinal_maps",
    "covariate_ordinal_unknown_value",
    "covariate_categorical_columns",
    "covariate_missing_numeric_strategy",
    "covariate_standardize_numeric",
    "covariates_strict_join",
}

TABULAR_PARAM_KEYS = {
    "tabular_model_type",
    "tabular_methods",
    "tabular_method_selection_metric",
    "tabular_method_selection_stat",
    "tabular_save_train_dataset",
    "tabular_reuse_train_dataset",
    "tabular_train_dataset_path",
    "tabular_save_test_dataset",
    "tabular_test_dataset_path",
}

GENERATIVE_PARAM_KEYS = {
    "generative_latent_dim",
    "generative_kl_weight",
    "generative_density_type",
    "generative_epochs",
    "generative_batch_size",
    "generative_seed",
    "generative_calibrate",
    "generative_covariates_strict",
}


def _migrate_validation_section(validation: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    before = dict(validation)
    backend_profiles = BackendProfilesConfig().model_dump(mode="python")
    active_backend = str(before.get("model_backend") or "ecdf").strip().lower()
    if active_backend not in {"ecdf", "tabular_sklearn", "generative_hybrid"}:
        active_backend = "ecdf"
    for backend in ("ecdf", "tabular_sklearn", "generative_hybrid"):
        backend_profiles[backend]["enabled"] = backend == active_backend
    for key in SHARED_PARAM_KEYS:
        if key in before:
            for backend in ("ecdf", "tabular_sklearn", "generative_hybrid"):
                backend_profiles[backend]["params"][key] = before[key]
    for key in TABULAR_PARAM_KEYS:
        if key in before:
            backend_profiles["tabular_sklearn"]["params"][key] = before[key]
    for key in GENERATIVE_PARAM_KEYS:
        if key in before:
            backend_profiles["generative_hybrid"]["params"][key] = before[key]
    if "ecdf_second_stage_enabled" in before:
        backend_profiles["ecdf"]["params"]["ecdf_second_stage_enabled"] = before["ecdf_second_stage_enabled"]
    migrated = {k: v for k, v in before.items() if k not in LEGACY_BACKEND_KEYS and k != "backend_profiles"}
    migrated["backend_profiles"] = backend_profiles
    moved = sorted(k for k in before.keys() if k in LEGACY_BACKEND_KEYS)
    return migrated, {"active_backend": active_backend, "moved_keys": moved}


def _validate_project_payload(project_data: Dict[str, Any], project_path: Path) -> None:
    validation = project_data.get("step_config", {}).get("validation")
    if not isinstance(validation, dict):
        raise ValueError("project.json does not contain step_config.validation object")
    cohorts = infer_monte_carlo_cohorts_from_project(project_data, project_path)
    payload = {
        "samples_base_path": project_data.get("samples_base_path", "/work/prostate-cancer/samples"),
        "base_project": str(project_path),
        "output_base": project_data.get("output_base", "/work/prostate-cancer"),
        "path_remap": project_data.get("path_remap"),
        "cohorts": cohorts,
        **validation,
    }
    MonteCarloConfig.model_validate(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy validation backend keys to backend_profiles.")
    parser.add_argument("project_json", type=Path, help="Path to project.json")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input project.json")
    parser.add_argument("--output", type=Path, default=None, help="Write migrated config to a new file")
    args = parser.parse_args()

    if args.in_place and args.output is not None:
        raise SystemExit("Use either --in-place or --output, not both.")

    project_path = args.project_json.resolve()
    project_data = json.loads(project_path.read_text(encoding="utf-8"))
    validation = project_data.get("step_config", {}).get("validation")
    if not isinstance(validation, dict):
        raise SystemExit("project.json is missing step_config.validation.")

    migrated_validation, summary = _migrate_validation_section(validation)
    project_data.setdefault("step_config", {})["validation"] = migrated_validation
    _validate_project_payload(project_data, project_path)

    output_payload = json.dumps(project_data, indent=2)
    if args.in_place:
        project_path.write_text(output_payload + "\n", encoding="utf-8")
        target = project_path
    elif args.output is not None:
        args.output.write_text(output_payload + "\n", encoding="utf-8")
        target = args.output
    else:
        target = None

    print(f"Active backend migrated from legacy key: {summary['active_backend']}")
    print(f"Legacy keys moved to backend_profiles: {summary['moved_keys']}")
    if target is not None:
        print(f"Wrote migrated project to: {target}")
    else:
        print("Dry run complete. Use --in-place or --output to write migrated JSON.")


if __name__ == "__main__":
    main()
