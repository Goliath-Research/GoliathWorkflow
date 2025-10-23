from pydantic import Field, field_validator
from typing import Optional
from pydantic import BaseModel


class ClassifierConfig(BaseModel):
    # Prediction parameters
    temperature: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Temperature for softmax in prediction"
    )
    enable_platt_calibration: bool = Field(
        default=False,
        description="Enable Platt scaling calibration on validation data"
    )
    validation_data_path: Optional[str] = Field(
        default=None,
        description="Path to validation data for Platt calibration (JSON or HDF5 with 'X' and 'y' datasets)"
    )

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        if v < 0.1:
            raise ValueError("Temperature must be >= 0.1")
        if v > 10.0:
            raise ValueError("Temperature must be <= 10.0")
        return v
