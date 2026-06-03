"""
Registry of pipeline Pydantic config models and their committed JSON Schema artifact paths.

Pydantic models are the source of truth; schemas under ``schemas/config/`` are generated artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import List, Sequence, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class ConfigSchemaSpec:
    """One config model and its committed JSON Schema file (relative to repo ``schemas/config/``)."""

    schema_id: str
    module: str
    class_name: str
    filename: str
    title: str | None = None

    def load_model(self) -> Type[BaseModel]:
        mod = import_module(self.module)
        model = getattr(mod, self.class_name, None)
        if model is None:
            raise AttributeError(f"{self.module}.{self.class_name} not found")
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            raise TypeError(f"{self.module}.{self.class_name} is not a Pydantic BaseModel")
        return model


# Committed artifact root: <repo>/schemas/config/
CONFIG_SCHEMA_SPECS: Sequence[ConfigSchemaSpec] = (
    ConfigSchemaSpec(
        schema_id="project",
        module="methyl_utils.pipeline_config",
        class_name="ProjectConfig",
        filename="project_config.schema.json",
        title="ProjectConfig",
    ),
    ConfigSchemaSpec(
        schema_id="validation_monte_carlo",
        module="methyl_validation.config",
        class_name="MonteCarloConfig",
        filename="validation_monte_carlo.schema.json",
        title="MonteCarloConfig",
    ),
    ConfigSchemaSpec(
        schema_id="validation_step",
        module="methyl_validation.config",
        class_name="ValidationStepConfig",
        filename="validation.schema.json",
        title="ValidationStepConfig",
    ),
    ConfigSchemaSpec(
        schema_id="validation_regulatory",
        module="methyl_validation.config",
        class_name="RegulatoryLifecycleConfig",
        filename="validation_regulatory.schema.json",
        title="RegulatoryLifecycleConfig",
    ),
    ConfigSchemaSpec(
        schema_id="validation_feature_selection",
        module="methyl_validation.config",
        class_name="FeatureSelectionConfig",
        filename="validation_feature_selection.schema.json",
        title="FeatureSelectionConfig",
    ),
    ConfigSchemaSpec(
        schema_id="validation_partitions",
        module="methyl_validation.config",
        class_name="ValidationPartitionContract",
        filename="validation_partitions.schema.json",
        title="ValidationPartitionContract",
    ),
    ConfigSchemaSpec(
        schema_id="validation_backend_profiles",
        module="methyl_validation.config",
        class_name="BackendProfilesConfig",
        filename="validation_backend_profiles.schema.json",
        title="BackendProfilesConfig",
    ),
    ConfigSchemaSpec(
        schema_id="detection",
        module="methyl_detector.models.config",
        class_name="MethylDetectorConfig",
        filename="detection.schema.json",
        title="MethylDetectorConfig",
    ),
    ConfigSchemaSpec(
        schema_id="mapper",
        module="methyl_mapper.config",
        class_name="MapperStepConfig",
        filename="mapper.schema.json",
        title="MapperStepConfig",
    ),
    ConfigSchemaSpec(
        schema_id="enricher",
        module="methyl_enricher.config",
        class_name="EnricherStepConfig",
        filename="enricher.schema.json",
        title="EnricherStepConfig",
    ),
    ConfigSchemaSpec(
        schema_id="classifier",
        module="methyl_classifier.models.config_schema",
        class_name="ClassificationConfig",
        filename="classifier.schema.json",
        title="ClassificationConfig",
    ),
    ConfigSchemaSpec(
        schema_id="predictor",
        module="methyl_predictor.models.config",
        class_name="PredictorConfig",
        filename="predictor.schema.json",
        title="PredictorConfig",
    ),
    ConfigSchemaSpec(
        schema_id="alignment_qc",
        module="methyl_alignment_qc.models.config",
        class_name="AlignmentQCConfig",
        filename="alignment_qc.schema.json",
        title="AlignmentQCConfig",
    ),
    ConfigSchemaSpec(
        schema_id="centroid",
        module="methyl_centroid.config",
        class_name="MethylCentroidConfig",
        filename="centroid.schema.json",
        title="MethylCentroidConfig",
    ),
    ConfigSchemaSpec(
        schema_id="progression",
        module="methyl_disease_progression.config",
        class_name="ProgressionStepConfig",
        filename="progression.schema.json",
        title="ProgressionStepConfig",
    ),
    ConfigSchemaSpec(
        schema_id="queue_discovery_task",
        module="methyl_validation.task_schema",
        class_name="DiscoveryRunTaskV1",
        filename="queue_discovery_task_v1.schema.json",
        title="DiscoveryRunTaskV1",
    ),
    ConfigSchemaSpec(
        schema_id="alignment_qc_export_v1",
        module="methyl_alignment_qc.models.sample_qc",
        class_name="ExportedSampleQCPayload",
        filename="alignment_qc/exported_sample_qc.schema.json",
        title="ExportedSampleQCPayload",
    ),
    ConfigSchemaSpec(
        schema_id="alignment_qc_export_v2",
        module="methyl_alignment_qc.models.sample_qc_v2",
        class_name="ExportedSampleQCV2Payload",
        filename="alignment_qc/exported_sample_qc_v2.schema.json",
        title="ExportedSampleQCV2Payload",
    ),
)


def list_config_schema_specs() -> List[ConfigSchemaSpec]:
    return list(CONFIG_SCHEMA_SPECS)
