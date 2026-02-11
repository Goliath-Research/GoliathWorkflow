"""
Shared pipeline project configuration for MethylPipeline workflows.

Defines Pydantic models for a single project config (two groups, output_base)
and derived paths under {output_base}/centroids|detection|mapper|enricher|classifier.
Used by MethylCentroid, MethylDetector, MethylMapper, MethylEnricher, MethylClassifier
to avoid repeating sample paths and output layout across configs.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class GroupConfig(BaseModel):
    """One cohort (e.g. healthy or disease)."""

    label: str = Field(..., description="Group label; used for centroid subdir name (e.g. healthy, pcancer)")
    sample_paths: List[str] = Field(
        default_factory=list,
        description="List of sample directory paths, or paths to files containing one path per line / JSON array",
    )

    @field_validator("label")
    @classmethod
    def label_non_empty(cls, v: str) -> str:
        if not (v and v.strip()):
            raise ValueError("label must be non-empty")
        return v.strip()


class DerivedPaths(BaseModel):
    """
    Derived paths from a ProjectConfig.
    Convention: {output_base}/{centroids|detection|mapper|enricher|classifier}.
    """

    output_base: str = Field(..., description="Project root directory")
    centroid1_dir: str = Field(..., description="Centroid directory for group1")
    centroid2_dir: str = Field(..., description="Centroid directory for group2")
    detection_dir: str = Field(..., description="MethylDetector output directory")
    mapper_dir: str = Field(..., description="MethylMapper output directory")
    enricher_dir: str = Field(..., description="MethylEnricher output directory")
    classifier_dir: str = Field(..., description="MethylClassifier output directory")

    @property
    def mapper_combined_csv(self) -> str:
        """Typical MethylMapper combined gene CSV path."""
        return str(Path(self.mapper_dir) / "all-gene_name-combined.csv")


class ProjectConfig(BaseModel):
    """
    Single source of truth for a two-group MethylPipeline project.
    Defines groups, output layout, and optional shared parameters.
    """

    project_name: str = Field(
        ...,
        description="Project identifier for metadata and naming (e.g. PCa_vs_Healthy)",
    )
    output_base: str = Field(
        ...,
        description="Project root; under it: centroids, detection, mapper, enricher, classifier",
    )
    group1: GroupConfig = Field(..., description="First cohort (e.g. control/healthy)")
    group2: GroupConfig = Field(..., description="Second cohort (e.g. disease/cancer)")
    chromosomes: Optional[List[str]] = Field(
        default=None,
        description="Shared chromosome list (e.g. ['1','2',...,'X','Y'])",
    )
    contexts: Optional[List[str]] = Field(
        default=None,
        description="Shared contexts (e.g. ['CG'])",
    )
    path_remap: Optional[Dict[str, str]] = Field(
        default=None,
        description="Prefix replacement when sample paths moved (e.g. NAS); longest match applied",
    )
    step_config: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Optional per-step configuration. Keys: centroid, detection, mapper, enricher, classifier. "
        "Values are merged into that step's config (override file / CLI still override these).",
    )

    @field_validator("output_base")
    @classmethod
    def output_base_stripped(cls, v: str) -> str:
        return v.rstrip("/") if v else v

    def get_derived_paths(self) -> DerivedPaths:
        """Compute derived paths from this project config."""
        base = self.output_base.rstrip("/")
        return DerivedPaths(
            output_base=base,
            centroid1_dir=f"{base}/centroids/{self.group1.label}",
            centroid2_dir=f"{base}/centroids/{self.group2.label}",
            detection_dir=f"{base}/detection",
            mapper_dir=f"{base}/mapper",
            enricher_dir=f"{base}/enricher",
            classifier_dir=f"{base}/classifier",
        )

    def get_group1_sample_paths(self) -> List[str]:
        """Return resolved sample paths for group1 (expand list-file paths if needed)."""
        return _resolve_sample_paths(self.group1.sample_paths)

    def get_group2_sample_paths(self) -> List[str]:
        """Return resolved sample paths for group2."""
        return _resolve_sample_paths(self.group2.sample_paths)

    def get_step_config(self, step_name: str) -> Dict[str, Any]:
        """
        Return the config dict for a step, or empty dict if not defined.
        Step names: centroid, detection, mapper, enricher, classifier.
        """
        if not self.step_config:
            return {}
        return dict(self.step_config.get(step_name) or {})


def _resolve_sample_paths(sample_paths: List[str]) -> List[str]:
    """Expand any path that points to a file (one path per line or JSON array) into a list of paths."""
    import json
    out: List[str] = []
    for p in sample_paths:
        p = p.strip()
        if not p:
            continue
        path = Path(p)
        if path.is_file():
            content = path.read_text().strip()
            if content.startswith("["):
                data = json.loads(content)
                out.extend([str(x).strip() for x in data if str(x).strip()])
            else:
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        out.append(line)
        else:
            out.append(p)
    return out


def load_project(path: Union[str, Path]) -> ProjectConfig:
    """Load and validate a project config from a JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project config not found: {path}")
    import json
    with open(path) as f:
        data = json.load(f)
    return ProjectConfig.model_validate(data)
