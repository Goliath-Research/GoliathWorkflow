"""
Configuration schema for MethylClassifier CLI
"""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class ClassificationConfig(BaseModel):
    """Configuration for sample classification."""
    
    # Required
    model_path: str = Field(
        ...,
        description="Path to trained classifier model (.pkl file)"
    )
    input_path: str = Field(
        ...,
        description="Path to input .h5 file or directory containing .h5 files"
    )
    
    # Optional
    output_path: Optional[str] = Field(
        default=None,
        description="Optional output CSV file for classification results"
    )
    
    prediction_method: Optional[str] = Field(
        default=None,
        description="Prediction method: 'sklearn' (fast), 'beta' (exact), or None (smart default based on DMPs)"
    )
    
    debug: bool = Field(
        default=False,
        description="Enable debug output"
    )
    
    no_filter: bool = Field(
        default=False,
        description="Process all .h5 files without chromosome/context filtering"
    )
    
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    class Config:
        """Pydantic config."""
        protected_namespaces = ()  # Allow 'model_' prefix
        json_schema_extra = {
            "example": {
                "model_path": "models/classifier-chr1-CG.pkl",
                "input_path": "samples/",
                "output_path": "results/classification_results.csv",
                "prediction_method": "sklearn",
                "debug": False,
                "no_filter": False,
                "log_level": "INFO"
            }
        }
    
    @classmethod
    def from_json(cls, config_path: Path) -> "ClassificationConfig":
        """Load configuration from JSON file."""
        import json
        with open(config_path, 'r') as f:
            data = json.load(f)
        return cls(**data)
    
    def to_json(self, output_path: Path) -> None:
        """Save configuration to JSON file."""
        import json
        with open(output_path, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)

