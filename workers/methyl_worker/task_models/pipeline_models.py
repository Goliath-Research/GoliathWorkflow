"""Strict Pydantic I/O models for pipeline workflow actions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ActionOutputBase


class StepOverrideConfig(BaseModel):
    """MC iteration overrides passed as stepOverride JSON."""

    model_config = ConfigDict(extra="forbid")

    base_config: Optional[Dict[str, Any]] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    comparison: Optional[str] = None
    output_dir: Optional[str] = None


class CentroidTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    group: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    comparison: Optional[str] = None
    outputDir: Optional[str] = None
    centroid1Dir: Optional[str] = None
    centroid2Dir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None
    addSamples: Optional[List[str]] = None
    removeSamples: Optional[List[str]] = None


class CentroidTaskOutput(ActionOutputBase):
    group: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    output_dir: Optional[str] = None
    centroid_h5_path: Optional[str] = None
    n_samples: Optional[int] = None
    n_positions: Optional[int] = None


class DetectorTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    group: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    comparison: Optional[str] = None
    outputDir: Optional[str] = None
    centroid1Dir: Optional[str] = None
    centroid2Dir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None
    fixedDmpPanel: Optional[str] = None


class DetectorTaskOutput(ActionOutputBase):
    group: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    output_dir: Optional[str] = None
    n_statistical_dmps: Optional[int] = None
    n_biological_dmps: Optional[int] = None
    discovery_csv: Optional[str] = None
    result_json_path: Optional[str] = None


class MapperTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    group: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    comparison: Optional[str] = None
    outputDir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None


class MapperTaskOutput(ActionOutputBase):
    group: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    output_dir: Optional[str] = None
    n_input_dmps: Optional[int] = None
    n_output_genes: Optional[int] = None
    output_csv: Optional[str] = None
    output_json: Optional[str] = None


class EnricherTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    group: Optional[str] = None
    comparison: Optional[str] = None
    outputDir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None


class EnricherTaskOutput(ActionOutputBase):
    comparison: Optional[str] = None
    output_dir: Optional[str] = None
    all_complete: Optional[bool] = None
    completeness_manifest_path: Optional[str] = None
    n_comparisons: Optional[int] = None


class ProgressionTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    orderedComparisonLabels: Optional[List[str]] = None
    outputDir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None


class ProgressionTaskOutput(ActionOutputBase):
    output_dir: Optional[str] = None
    n_comparisons: Optional[int] = None
    summary_path: Optional[str] = None


class ClassifierTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    group: Optional[str] = None
    outputDir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None
    fixedDmpPanel: Optional[str] = None


class ClassifierTaskOutput(ActionOutputBase):
    output_dir: Optional[str] = None
    model_path: Optional[str] = None
    n_features: Optional[int] = None


class PredictorTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    group: Optional[str] = None
    outputDir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None


class PredictorTaskOutput(ActionOutputBase):
    output_dir: Optional[str] = None
    validation_metrics_path: Optional[str] = None
    balanced_accuracy: Optional[float] = None


class ClusterTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    group: Optional[str] = None
    outputDir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None


class ClusterTaskOutput(ActionOutputBase):
    group: Optional[str] = None
    output_dir: Optional[str] = None
    n_clusters: Optional[int] = None
    n_noise: Optional[int] = None
    manifest_path: Optional[str] = None


class DmpSelectTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylDmpSelect"
    projectPath: Optional[str] = None
    project: Optional[str] = None
    group: Optional[str] = None
    chromosome: str
    context: Optional[Union[str, List[str]]] = None
    comparison: Optional[str] = None
    discoveryCsv: Optional[str] = None
    outputDir: Optional[str] = None
    stepOverride: Optional[StepOverrideConfig] = None

    @model_validator(mode="after")
    def _project_required(self) -> "DmpSelectTaskInput":
        if not (self.projectPath or self.project):
            raise ValueError("projectPath or project is required")
        return self


class DmpSelectTaskOutput(ActionOutputBase):
    chromosome: Optional[str] = None
    n_dmps_discovery: Optional[int] = None
    n_dmps_classifier: Optional[int] = None
    n_dmps_extended: Optional[int] = None
    discovery_csv: Optional[str] = None
    classifier_csv: Optional[str] = None
    extended_csv: Optional[str] = None
    audit_path: Optional[str] = None


class GeneSelectTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylGeneSelect"
    projectPath: Optional[str] = None
    project: Optional[str] = None
    runDir: str
    comparison: Optional[str] = None
    maxGenes: Optional[int] = Field(default=None, ge=1)
    maxDmps: Optional[int] = Field(default=None, ge=1)
    biomarkerFilter: bool = False

    @model_validator(mode="after")
    def _project_required(self) -> "GeneSelectTaskInput":
        if not (self.projectPath or self.project):
            raise ValueError("projectPath or project is required")
        return self


class GeneSelectTaskOutput(ActionOutputBase):
    run_dir: Optional[str] = None
    selected_k: Optional[int] = None
    balanced_accuracy: Optional[float] = None
    genes_classifier_csv: Optional[str] = None
    gene_dmp_loci_csv: Optional[str] = None
    metrics_json: Optional[str] = None


class GeneFeatureSelectTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylGeneFeatureSelect"
    mapperDir: str
    outputDir: str
    maxFeatures: Optional[int] = Field(default=None, ge=1)
    targetBalancedAccuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class GeneFeatureSelectTaskOutput(ActionOutputBase):
    n_features: Optional[int] = None
    output_csv: Optional[str] = None
    audit_path: Optional[str] = None


class BiomarkerFilterSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    mode: Optional[str] = None
    region_hits: List[str] = Field(default_factory=list)
    biomarker_pool_size: Optional[int] = None
    n_genes_in_mapper_after_intersect: Optional[int] = None
    ppi_cache_path: Optional[str] = None
    ppi_score_threshold: Optional[float] = None


class BiomarkerFilterTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "ValidationBiomarkerFilter"
    projectPath: Optional[str] = None
    project: Optional[str] = None
    runDir: Optional[str] = None

    @model_validator(mode="after")
    def _project_required(self) -> "BiomarkerFilterTaskInput":
        if not (self.projectPath or self.project):
            raise ValueError("projectPath or project is required")
        return self


class BiomarkerFilterTaskOutput(ActionOutputBase):
    n_genes: int
    outputCsv: str
    biomarker_filter: BiomarkerFilterSummary
