"""Strict Pydantic I/O models for split-detector workflow actions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DmpSelectTaskInput(BaseModel):
    """Input for pipeline.dmp_select (methyl-dmp-select)."""

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
    stepOverride: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _project_required(self) -> "DmpSelectTaskInput":
        if not (self.projectPath or self.project):
            raise ValueError("projectPath or project is required")
        return self


class DmpSelectTaskOutput(BaseModel):
    """Output for pipeline.dmp_select."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "skipped"] = "ok"
    tool: Optional[str] = None
    chromosome: Optional[str] = None
    n_dmps_discovery: Optional[int] = None
    n_dmps_classifier: Optional[int] = None
    n_dmps_extended: Optional[int] = None
    discovery_csv: Optional[str] = None
    classifier_csv: Optional[str] = None
    extended_csv: Optional[str] = None
    audit_path: Optional[str] = None
    stdout_tail: Optional[str] = None


class GeneSelectTaskInput(BaseModel):
    """Input for pipeline.gene_select (methyl-gene-select)."""

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


class GeneSelectTaskOutput(BaseModel):
    """Output for pipeline.gene_select."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    tool: Optional[str] = None
    run_dir: Optional[str] = None
    selected_k: Optional[int] = None
    balanced_accuracy: Optional[float] = None
    genes_classifier_csv: Optional[str] = None
    gene_dmp_loci_csv: Optional[str] = None
    metrics_json: Optional[str] = None
    stdout_tail: Optional[str] = None


class GeneFeatureSelectTaskInput(BaseModel):
    """Input for pipeline.gene_feature_select (methyl-gene-feature-select)."""

    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylGeneFeatureSelect"
    mapperDir: str
    outputDir: str
    maxFeatures: Optional[int] = Field(default=None, ge=1)
    targetBalancedAccuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class GeneFeatureSelectTaskOutput(BaseModel):
    """Output for pipeline.gene_feature_select."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "skipped"] = "ok"
    tool: Optional[str] = None
    n_features: Optional[int] = None
    output_csv: Optional[str] = None
    audit_path: Optional[str] = None
    stdout_tail: Optional[str] = None


class BiomarkerFilterTaskInput(BaseModel):
    """Input for validation.biomarker_filter."""

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


class BiomarkerFilterSummary(BaseModel):
    """Biomarker filter diagnostics written to gene_stability artifacts."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    mode: Optional[str] = None
    region_hits: List[str] = Field(default_factory=list)
    biomarker_pool_size: Optional[int] = None
    n_genes_in_mapper_after_intersect: Optional[int] = None
    ppi_cache_path: Optional[str] = None
    ppi_score_threshold: Optional[float] = None


class BiomarkerFilterTaskOutput(BaseModel):
    """Output for validation.biomarker_filter."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    n_genes: int
    outputCsv: str
    biomarker_filter: BiomarkerFilterSummary
