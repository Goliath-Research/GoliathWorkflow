"""Pydantic config for MethylPredictor."""

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PredictorConfig(BaseModel):
    """Configuration for running MethylPredictor on test sample sets."""

    model_path: Optional[str] = Field(
        default=None,
        description="Path to trained classifier .pkl file (single-file mode).",
    )
    model_dir: Optional[str] = Field(
        default=None,
        description="Path to directory containing classifier-{chrom}.pkl files (multi-chromosome mode).",
    )
    output_dir: str = Field(
        ...,
        description="Directory for validation_metrics.json and predictions CSV.",
    )
    test_control_paths: List[str] = Field(
        default_factory=list,
        description="Sample directory paths for control/class-0 test set.",
    )
    test_disease_paths: List[str] = Field(
        default_factory=list,
        description="Sample directory paths for disease/class-1 test set.",
    )
    path_remap: Optional[Dict[str, str]] = Field(
        default=None,
        description="Prefix replacement for sample paths: {\"old_prefix\": \"new_prefix\"}. Applied when paths come from config.",
    )
    samples_base_path: Optional[str] = Field(
        default=None,
        description="Base directory to resolve relative sample paths (project-level).",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug output.",
    )

    class Config:
        """Pydantic config."""
        protected_namespaces = ()
