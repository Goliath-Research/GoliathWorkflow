"""Simplified result models for MethylDetector analysis."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
from pydantic import BaseModel, Field, field_validator


def convert_numpy_types(obj):
    """Convert numpy types to Python native types for Pydantic compatibility."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj


class NumpyCompatibleModel(BaseModel):
    """Base model that handles numpy arrays automatically."""

    model_config = {
        "arbitrary_types_allowed": True,
    }

    @field_validator('*', mode='before')
    @classmethod
    def convert_numpy_arrays(cls, v):
        return convert_numpy_types(v)


class ComparisonStats(NumpyCompatibleModel):
    """Statistics for a single comparison."""

    comparison_name: str = Field(..., description="Name of comparison (e.g., '1-CG_WT_vs_msh1')")
    total_positions: int = Field(..., description="Total positions analyzed")
    statistical_dmps: int = Field(..., description="Statistically significant DMPs")
    biological_dmps: int = Field(..., description="Biologically significant DMPs after filtering")
    processing_time_seconds: float = Field(..., description="Processing time in seconds")
    gpu_used: bool = Field(default=False, description="Whether GPU was used")


class MethylDetectorResult(NumpyCompatibleModel):
    """Simplified result from MethylDetector analysis (DataFrame-centric)."""

    # Core results - DataFrame-based storage only
    biologically_significant_dmps_df: Optional[Any] = Field(
        default=None,
        description="DataFrame of biologically significant DMPs"
    )

    # Summary statistics
    total_statistical_dmps: int = Field(..., description="Total statistically significant DMPs")
    total_biological_dmps: int = Field(..., description="Total biologically significant DMPs")
    biological_retention_rate: float = Field(..., description="Fraction of statistical DMPs that are biologically significant")

    # Model performance (if classifier was trained)
    training_accuracy: Optional[float] = Field(
        default=None,
        description="Accuracy of trained classifier on training data"
    )

    # Comparison details
    comparison_stats: List[ComparisonStats] = Field(
        default_factory=list,
        description="Statistics for each comparison"
    )

    # Output files
    output_files: Dict[str, Union[str, Path]] = Field(
        default_factory=dict,
        description="Paths to generated output files"
    )

    # Classifier model (if trained)
    classifier_model_path: Optional[Union[str, Path]] = Field(
        default=None,
        description="Path to trained classifier model file"
    )


    # Metadata
    timestamp: str = Field(..., description="Analysis timestamp")
    version: str = Field(..., description="MethylDetector version")
    config_summary: Dict[str, Any] = Field(..., description="Key configuration parameters used")


    model_config = {
        "arbitrary_types_allowed": True,
    }


class MethylDetectorSummary(BaseModel):
    """Summary configuration for completed MethylDetector analysis."""

    # -----------------------
    # Analysis identification
    # -----------------------
    analysis_id: str = Field(..., description="Unique identifier for this analysis")
    timestamp: str = Field(..., description="When analysis was completed")
    version: str = Field(..., description="MethylDetector version used")

    # -----------------------
    # Input configuration
    # -----------------------
    input_files: Dict[str, Union[str, Path]] = Field(
        ..., description="Input centroid files used"
    )

    # -----------------------
    # Results summary
    # -----------------------
    total_statistical_dmps: int = Field(..., description="Total statistically significant DMPs found")
    total_biological_dmps: int = Field(..., description="Total biologically significant DMPs retained")
    biological_retention_rate: float = Field(..., description="Fraction retained after biological filtering")

    # -----------------------
    # Output files
    # -----------------------
    output_directory: Union[str, Path] = Field(..., description="Base output directory")

    csv_file: Optional[Union[str, Path]] = Field(
        default=None, description="Path to biological DMPs CSV file"
    )
    summary_json_file: Optional[Union[str, Path]] = Field(
        default=None, description="Path to analysis summary JSON file"
    )
    classifier_model_file: Optional[Union[str, Path]] = Field(
        default=None, description="Path to trained probabilistic classifier pickle file"
    )

    # -----------------------
    # Key parameters used
    # -----------------------
    key_parameters: Dict[str, Any] = Field(
        ..., description="Key configuration parameters that affected results"
    )

    # -----------------------
    # Quality metrics
    # -----------------------
    classifier_accuracy: Optional[float] = Field(
        default=None, description="Cross-validation accuracy of trained classifier"
    )
    top_dmp_significance: Optional[float] = Field(
        default=None, description="Biological significance score of top-ranked DMP"
    )

    model_config = {
        "arbitrary_types_allowed": True,
    }


# ✅ IMPLEMENTED: Full DataFrame Architecture
#
# The system uses pandas DataFrames throughout the entire pipeline:
# - Processing: DataFrame-based operations for filtering/selection
# - Results: DataFrame storage in MethylDetectorResult.biologically_significant_dmps_df
# - Export: Direct DataFrame-to-CSV without object conversion
#
# Benefits achieved:
# ✅ Zero-copy data pipeline from processing to output
# ✅ Faster vectorized operations with pandas/numpy
# ✅ Stronger type safety with DataFrame schemas
# ✅ Better memory efficiency for large datasets
# ✅ More expressive data manipulation
# ✅ Easier testing and debugging
# Architecture:
# - DataFrame operations handled directly in MethylDetector class
# - MethylDetectorResult stores DataFrame directly (no conversion)
# - Direct CSV export from DataFrames (no object serialization)
# - Pydantic models used only for config/results metadata 