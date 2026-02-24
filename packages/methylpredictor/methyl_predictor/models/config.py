"""Pydantic config for MethylPredictor."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


def _to_absolute_paths(paths: List[str], base_path: Optional[str]) -> List[str]:
    """Resolve each path to absolute; relative paths are resolved against base_path or cwd."""
    base = Path(base_path).resolve() if base_path else Path.cwd()
    result: List[str] = []
    for p in paths:
        if not p or not str(p).strip():
            continue
        path = Path(p.strip())
        if not path.is_absolute():
            path = base / path
        result.append(str(path.resolve()))
    return result


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
    test_group_paths: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="For multi-class: list of {label: str, paths: list} or {class_index: int, paths: list}. "
        "Order must match classifier class_names. Resolved to absolute paths.",
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

    @model_validator(mode="after")
    def ensure_absolute_test_paths(self) -> "PredictorConfig":
        """Normalize test_control_paths, test_disease_paths, and test_group_paths to absolute paths."""
        self.test_control_paths = _to_absolute_paths(
            self.test_control_paths, self.samples_base_path
        )
        self.test_disease_paths = _to_absolute_paths(
            self.test_disease_paths, self.samples_base_path
        )
        if self.test_group_paths:
            base = self.samples_base_path
            for entry in self.test_group_paths:
                paths = entry.get("paths")
                if isinstance(paths, list):
                    entry["paths"] = _to_absolute_paths(paths, base)
        return self

    class Config:
        """Pydantic config."""
        protected_namespaces = ()
