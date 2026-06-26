"""
Build ValidationPipeline context_json (iterations[]) from Monte Carlo stratified splits.

Used by:
- workers/methyl_worker ``validation.plan-iterations`` capability
- middle-tier REST ``POST /v1/validation/plan-iterations``
- ``methyl-validation plan-workflow-context`` CLI
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .cohort_inference import infer_monte_carlo_cohorts_from_project
from .config import MonteCarloConfig
from .mc_config_load import write_mc_config_snapshot
from .mc_manifest import write_detector_featurecuts_override, write_mapper_classifier_override
from .project_gen import (
    build_group_centroid_scope,
    carry_forward_centroids_from_previous_run,
    centroid_override_has_remove_samples,
    generate_run_project,
    generate_run_project_hierarchical_multiclass,
    generate_run_project_multiclass,
    infer_monte_carlo_layout,
    prepare_incremental_centroid_baseline,
)
from .split import load_and_resolve_sample_paths, stratified_split, stratified_split_multiclass
from .storage_layout import mc_config_snapshot_path


def _tag_iteration_as_stratified_draw(
    iteration: Dict[str, Any],
    *,
    run_dir: Path,
    layout: str,
    cohort_labels: List[str],
    config: MonteCarloConfig,
    seed: Optional[int],
) -> Dict[str, Any]:
    """Attach tagged ``StratifiedCohortDraw`` fields (backward-compatible with flat keys)."""
    from methyl_domain.helpers import (
        build_stratified_cohort_draw,
        comparisons_from_project_json,
        groups_from_mc_run_dir,
    )

    project_path = Path(iteration["projectPath"])
    groups = groups_from_mc_run_dir(
        run_dir, project_path, layout=layout, cohort_labels=cohort_labels
    )
    comparisons = comparisons_from_project_json(project_path)
    tagged = build_stratified_cohort_draw(
        run_id=str(iteration["runId"]),
        phase=str(iteration["phase"]),
        project_path=str(project_path.resolve()),
        groups=groups,
        comparisons=comparisons,
        seed=seed,
        train_fraction=config.train_fraction,
        task_config=iteration.get("taskConfig"),
    )
    return {**iteration, **tagged}

__all__ = [
    "ValidationPlanRequest",
    "plan_validation_context",
    "resolve_base_project_json",
]


class ValidationPlanRequest(BaseModel):
    """Input for validation.plan-iterations (worker or REST)."""

    projectPath: str = Field(..., description="Path to base project.json or project directory")
    featureIterations: Optional[int] = Field(None, ge=1)
    qualityIterations: Optional[int] = Field(None, ge=0)
    seed: Optional[int] = None
    trainFraction: Optional[float] = Field(None, gt=0.0, lt=1.0)
    layout: Optional[str] = Field(None, description="binary | multiclass | hierarchical_multiclass")
    overwrite: bool = False
    workerToolMapper: str = "MethylMapper"
    workerToolEnricher: str = "MethylEnricher"
    workerToolProgression: str = "MethylDiseaseProgression"
    orderedComparisonLabels: Optional[List[str]] = None


def resolve_base_project_json(project_path: str | Path) -> Path:
    """Resolve projectPath to the base project.json file."""
    path = Path(project_path).expanduser().resolve()
    if path.is_file() and path.suffix.lower() == ".json":
        return path
    if path.is_dir():
        candidate = path / "project.json"
        if candidate.is_file():
            return candidate
        configs = sorted(path.glob("project*.json"))
        if len(configs) == 1:
            return configs[0]
        if configs:
            return configs[0]
    raise FileNotFoundError(f"Could not resolve base project.json from projectPath={project_path!r}")


def _load_config_from_project(base_project: Path, request: ValidationPlanRequest) -> MonteCarloConfig:
    from methyl_utils import load_project
    from methyl_utils.action_config_resolver import resolve_for_project

    project = load_project(str(base_project))
    validation = resolve_for_project("validation", project)
    if not validation:
        raise ValueError(f"Project {base_project} missing resolved validation action config")

    with open(base_project, encoding="utf-8") as f:
        project_data = json.load(f)

    cohorts = infer_monte_carlo_cohorts_from_project(project_data, str(base_project))
    if len(cohorts) < 2:
        raise ValueError(
            "Could not infer >=2 Monte Carlo cohorts from project controls/diseases sample_paths."
        )

    mc_dict: Dict[str, Any] = {
        "samples_base_path": project_data.get("samples_base_path", "/work/prostate-cancer/samples"),
        "base_project": str(base_project),
        "output_base": project_data.get("output_base", "/work/prostate-cancer"),
        "path_remap": project_data.get("path_remap"),
        "cohorts": cohorts,
        **dict(validation),
    }
    config = MonteCarloConfig.model_validate(mc_dict)

    feature_n = request.featureIterations if request.featureIterations is not None else config.n_iterations
    updates: Dict[str, Any] = {"n_iterations": int(feature_n)}
    if request.seed is not None:
        updates["seed"] = int(request.seed)
    if request.trainFraction is not None:
        updates["train_fraction"] = float(request.trainFraction)
    return config.model_copy(update=updates)


def _monte_carlo_runs_root(config: MonteCarloConfig, base_project: Path) -> Tuple[Path, str]:
    from methyl_utils import load_project

    project_cfg = load_project(str(base_project))
    output_base = Path(config.output_base)
    output_base.mkdir(parents=True, exist_ok=True)
    runs_root = output_base / project_cfg.project_name / "monte_carlo_runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    project_root = str(output_base / project_cfg.project_name)
    return runs_root, project_root


def _comparison_labels(base_project: Path, request: ValidationPlanRequest) -> List[str]:
    if request.orderedComparisonLabels:
        return list(request.orderedComparisonLabels)
    with open(base_project, encoding="utf-8") as f:
        raw = json.load(f)
    comparisons = raw.get("comparisons") or []
    labels = [str(c.get("label") or c.get("name") or "") for c in comparisons if isinstance(c, dict)]
    labels = [x for x in labels if x]
    if labels:
        return labels
    return ["validation"]


def _materialize_iteration(
    *,
    config: MonteCarloConfig,
    base_project: Path,
    monte_carlo_runs_root: Path,
    layout: str,
    cohort_paths_list: List[Tuple[str, List[str]]],
    cohort_labels: List[str],
    phase: str,
    phase_index: int,
    global_run_number: int,
    seed_offset: int,
    previous_train_control: Optional[List[str]],
    previous_train_disease: Optional[List[str]],
    previous_train_by_label: Optional[Dict[str, List[str]]],
    previous_run_dir: Optional[Path],
    overwrite: bool,
) -> Tuple[
    Dict[str, Any],
    Optional[List[str]],
    Optional[List[str]],
    Optional[Dict[str, List[str]]],
    Optional[Path],
]:
    run_dir_name = f"run_{global_run_number:04d}"
    run_dir = monte_carlo_runs_root / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    display_run_id = f"{phase}_run_{phase_index:04d}"
    seed_i = (int(config.seed) + seed_offset) if config.seed is not None else None

    control_paths = cohort_paths_list[0][1] if layout == "binary" else []
    disease_paths = cohort_paths_list[1][1] if layout == "binary" else []

    if layout == "binary":
        train_control, train_disease, val_control, val_disease = stratified_split(
            control_paths, disease_paths, config.train_fraction, seed=seed_i
        )
    else:
        train_m, val_m = stratified_split_multiclass(
            cohort_paths_list, config.train_fraction, seed=seed_i
        )

    project_path = run_dir / "project.json"
    if project_path.is_file() and not overwrite:
        task_config = {
            "runId": display_run_id,
            "phase": phase,
            "iteration": phase_index,
            "layout": layout,
            "trainFraction": config.train_fraction,
            "seed": seed_i,
            "projectJson": str(project_path.resolve()),
            "runDir": str(run_dir.resolve()),
            "monteCarloRunsRoot": str(monte_carlo_runs_root.resolve()),
        }
        iteration = {
            "runId": display_run_id,
            "phase": phase,
            "projectPath": str(project_path.resolve()),
            "taskConfig": task_config,
        }
        return (
            _tag_iteration_as_stratified_draw(
                iteration,
                run_dir=run_dir,
                layout=layout,
                cohort_labels=cohort_labels,
                config=config,
                seed=seed_i,
            ),
            previous_train_control,
            previous_train_disease,
            previous_train_by_label,
            previous_run_dir,
        )

    det_override = write_detector_featurecuts_override(run_dir, config)
    if config.stability_gene_featurecuts_enabled:
        write_mapper_classifier_override(run_dir, config)
    if config.stability_gene_biomarker_filter_enabled and not config.stability_mapper_enrich_disease:
        import warnings

        warnings.warn(
            "stability_gene_biomarker_filter_enabled with stability_mapper_enrich_disease=false "
            "may yield empty pools when enricher.disease_only=true (mapper disease columns missing).",
            stacklevel=2,
        )

    val_control_csv = None
    val_disease_csv = None
    val_groups_json = None
    centroid_overrides_by_label: Dict[str, Path] = {}
    c1 = None
    c2 = None

    if layout == "binary":
        (
            project_path,
            _t1,
            _t2,
            val_control_csv,
            val_disease_csv,
            c1,
            c2,
        ) = generate_run_project(
            base_project,
            run_dir,
            run_dir_name,
            str(monte_carlo_runs_root),
            train_control,
            train_disease,
            val_control,
            val_disease,
            config.samples_base_path,
            previous_train_control_paths=previous_train_control,
            previous_train_disease_paths=previous_train_disease,
        )
        previous_train_control = list(train_control)
        previous_train_disease = list(train_disease)
        prepare_incremental_centroid_baseline(previous_run_dir, run_dir, c1, c2)
    elif layout == "multiclass":
        project_path, val_groups_json = generate_run_project_multiclass(
            base_project,
            run_dir,
            run_dir_name,
            str(monte_carlo_runs_root),
            train_m,
            val_m,
            cohort_labels,
            config.samples_base_path,
        )
    else:
        project_path, val_groups_json, centroid_overrides_by_label = generate_run_project_hierarchical_multiclass(
            base_project,
            run_dir,
            run_dir_name,
            str(monte_carlo_runs_root),
            train_m,
            val_m,
            cohort_labels,
            config.samples_base_path,
            previous_train_by_label=previous_train_by_label,
        )

    if layout in {"multiclass", "hierarchical_multiclass"}:
        needs_baseline = any(
            centroid_override_has_remove_samples(path) for path in centroid_overrides_by_label.values()
        )
        if needs_baseline and previous_run_dir is not None:
            carry_forward_centroids_from_previous_run(previous_run_dir, run_dir)

    task_config = {
        "runId": display_run_id,
        "phase": phase,
        "iteration": phase_index,
        "layout": layout,
        "trainFraction": config.train_fraction,
        "seed": seed_i,
        "projectJson": str(project_path.resolve()),
        "runDir": str(run_dir.resolve()),
        "monteCarloRunsRoot": str(monte_carlo_runs_root.resolve()),
    }
    if det_override is not None:
        task_config["detectorStepOverride"] = str(det_override)
    if val_control_csv is not None:
        task_config["valControlCsv"] = str(val_control_csv)
    if val_disease_csv is not None:
        task_config["valDiseaseCsv"] = str(val_disease_csv)
    if val_groups_json is not None:
        task_config["valGroupsJson"] = str(val_groups_json)
    if c1 is not None:
        task_config["centroidGroup1Override"] = str(c1)
    if c2 is not None:
        task_config["centroidGroup2Override"] = str(c2)
    if centroid_overrides_by_label:
        task_config["centroidOverridesByLabel"] = {
            lbl: str(path) for lbl, path in centroid_overrides_by_label.items()
        }

    iteration = {
        "runId": display_run_id,
        "phase": phase,
        "projectPath": str(project_path.resolve()),
        "runDir": str(run_dir.resolve()),
        "taskConfig": task_config,
    }
    if layout in {"multiclass", "hierarchical_multiclass"}:
        iteration["centroidGroups"] = build_group_centroid_scope(
            base_project_path=project_path,
            cohort_labels=cohort_labels,
            train_by_label=train_m,
            previous_train_by_label=previous_train_by_label,
        )
        previous_train_by_label = {lbl: list(train_m[lbl]) for lbl in cohort_labels}
    if previous_run_dir is not None:
        iteration["previousRunDir"] = str(previous_run_dir.resolve())

    return (
        _tag_iteration_as_stratified_draw(
            iteration,
            run_dir=run_dir,
            layout=layout,
            cohort_labels=cohort_labels,
            config=config,
            seed=seed_i,
        ),
        previous_train_control,
        previous_train_disease,
        previous_train_by_label if layout in {"multiclass", "hierarchical_multiclass"} else None,
        run_dir,
    )


def plan_validation_context(request: ValidationPlanRequest | Dict[str, Any]) -> Dict[str, Any]:
    """
    Materialize Monte Carlo run directories and return ValidationPipeline ``context_json``.

    Writes per-run ``project.json`` + train/val CSVs under ``output_base/project_name/monte_carlo_runs/``.
    """
    if not isinstance(request, ValidationPlanRequest):
        request = ValidationPlanRequest.model_validate(request)

    base_project = resolve_base_project_json(request.projectPath)
    config = _load_config_from_project(base_project, request)
    monte_carlo_runs_root, project_root = _monte_carlo_runs_root(config, base_project)

    write_mc_config_snapshot(config, mc_config_snapshot_path(monte_carlo_runs_root))

    layout = request.layout or infer_monte_carlo_layout(base_project, len(config.cohorts))
    cohort_paths_list: List[Tuple[str, List[str]]] = []
    for cohort in config.cohorts:
        paths = load_and_resolve_sample_paths(cohort.csv, config.samples_base_path)
        if not paths:
            raise ValueError(f"Cohort {cohort.label!r} ({cohort.csv}) has no samples")
        cohort_paths_list.append((cohort.label, paths))
    cohort_labels = [c.label for c in config.cohorts]

    feature_n = request.featureIterations if request.featureIterations is not None else config.n_iterations
    quality_n = request.qualityIterations if request.qualityIterations is not None else 0

    iterations: List[Dict[str, Any]] = []
    previous_train_control: Optional[List[str]] = None
    previous_train_disease: Optional[List[str]] = None
    previous_train_by_label: Optional[Dict[str, List[str]]] = None
    previous_run_dir: Optional[Path] = None
    global_run = 0
    seed_offset = 0

    for phase, count in (("feature", feature_n), ("quality", quality_n)):
        if count <= 0:
            continue
        for phase_index in range(1, count + 1):
            global_run += 1
            (
                iteration,
                previous_train_control,
                previous_train_disease,
                previous_train_by_label,
                previous_run_dir,
            ) = _materialize_iteration(
                config=config,
                base_project=base_project,
                monte_carlo_runs_root=monte_carlo_runs_root,
                layout=layout,
                cohort_paths_list=cohort_paths_list,
                cohort_labels=cohort_labels,
                phase=phase,
                phase_index=phase_index,
                global_run_number=global_run,
                seed_offset=seed_offset,
                previous_train_control=previous_train_control,
                previous_train_disease=previous_train_disease,
                previous_train_by_label=previous_train_by_label,
                previous_run_dir=previous_run_dir,
                overwrite=request.overwrite,
            )
            iterations.append(iteration)
            seed_offset += 1

    if not iterations:
        raise ValueError("No iterations planned (featureIterations and qualityIterations are both zero)")

    plan_summary = {
        "baseProject": str(base_project),
        "layout": layout,
        "featureIterations": feature_n,
        "qualityIterations": quality_n,
        "seed": config.seed,
        "trainFraction": config.train_fraction,
        "monteCarloRunsRoot": str(monte_carlo_runs_root.resolve()),
        "iterations": iterations,
    }

    return {
        "projectPath": project_root,
        "workerToolMapper": request.workerToolMapper,
        "workerToolEnricher": request.workerToolEnricher,
        "workerToolProgression": request.workerToolProgression,
        "orderedComparisonLabels": _comparison_labels(base_project, request),
        "iterations": iterations,
        "validationPlan": plan_summary,
    }
