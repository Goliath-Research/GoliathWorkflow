"""
Registry of workflow action JSON Schema specs (input/output Pydantic models).

Source of truth for worker payload validation and schemas/tasks/*.schema.json export.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import List, Optional, Sequence, Tuple, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class TaskSchemaSpec:
    action_name: str
    schema_id: str
    input_module: str
    input_class: str
    output_module: str
    output_class: str

    def load_input_model(self) -> Type[BaseModel]:
        return _load_model(self.input_module, self.input_class)

    def load_output_model(self) -> Type[BaseModel]:
        return _load_model(self.output_module, self.output_class)

    @property
    def input_filename(self) -> str:
        safe = self.action_name.replace(".", "_")
        return f"{safe}.input.schema.json"

    @property
    def output_filename(self) -> str:
        safe = self.action_name.replace(".", "_")
        return f"{safe}.output.schema.json"


def _load_model(module: str, class_name: str) -> Type[BaseModel]:
    mod = import_module(module)
    model = getattr(mod, class_name, None)
    if model is None:
        raise AttributeError(f"{module}.{class_name} not found")
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError(f"{module}.{class_name} is not a Pydantic BaseModel")
    return model


_PIPELINE = (
    "methyl_worker.task_models",
    "PipelineCliTaskInput",
    "methyl_worker.task_models",
    "PipelineCliTaskOutput",
)
_SAMPLE_IN = ("methyl_worker.task_models", "SamplePrepTaskInput")

TASK_SCHEMA_SPECS: Sequence[TaskSchemaSpec] = (
    TaskSchemaSpec("pipeline.centroid", "pipeline.centroid", *_PIPELINE),
    TaskSchemaSpec("pipeline.detector", "pipeline.detector", *_PIPELINE),
    TaskSchemaSpec("pipeline.mapper", "pipeline.mapper", *_PIPELINE),
    TaskSchemaSpec("pipeline.enricher", "pipeline.enricher", *_PIPELINE),
    TaskSchemaSpec("pipeline.progression", "pipeline.progression", *_PIPELINE),
    TaskSchemaSpec(
        "sample.download_fastq",
        "sample.download_fastq",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DownloadFastqTaskOutput",
    ),
    TaskSchemaSpec(
        "sample.parabricks_fq2bam",
        "sample.parabricks_fq2bam",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "ParabricksTaskOutput",
    ),
    TaskSchemaSpec(
        "sample.delete_fastqs",
        "sample.delete_fastqs",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DeleteTaskOutput",
    ),
    TaskSchemaSpec(
        "sample.methyl_qc",
        "sample.methyl_qc",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MethylQcTaskOutput",
    ),
    TaskSchemaSpec(
        "sample.fragmentomics",
        "sample.fragmentomics",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "FragmentomicsTaskOutput",
    ),
    TaskSchemaSpec(
        "sample.methyl_extract",
        "sample.methyl_extract",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MethylExtractTaskOutput",
    ),
    TaskSchemaSpec(
        "sample.delete_bam",
        "sample.delete_bam",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DeleteTaskOutput",
    ),
    TaskSchemaSpec(
        "sample.qc_failed",
        "sample.qc_failed",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MarkFailedTaskOutput",
    ),
    TaskSchemaSpec(
        "validation.plan_iterations",
        "validation.plan_iterations",
        "methyl_validation.workflow_planner",
        "ValidationPlanRequest",
        "methyl_worker.task_models",
        "ValidationPlanTaskOutput",
    ),
)


def list_task_schema_specs() -> List[TaskSchemaSpec]:
    return list(TASK_SCHEMA_SPECS)


def find_task_schema_spec(action_name: str) -> Optional[TaskSchemaSpec]:
    for spec in TASK_SCHEMA_SPECS:
        if spec.action_name == action_name:
            return spec
    return None


def resolve_task_schema_spec(action_name: str, capability: Optional[str] = None) -> Optional[TaskSchemaSpec]:
    spec = find_task_schema_spec(action_name)
    if spec is not None:
        return spec
    if capability == "validation.plan-iterations":
        return find_task_schema_spec("validation.plan_iterations")
    return None
