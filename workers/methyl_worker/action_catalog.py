"""
Unified catalog of all workflow ACTION definitions.

Single source of truth for action_name, capability, handler dispatch, CLI/tool
mapping, task I/O schema models, and project.json step_config linkage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Literal, Optional, Sequence, Tuple

ActionCategory = Literal["sample_prep", "modeling", "validation"]
NodeType = Literal[
    "ACTION",
    "SEQUENCE",
    "PARALLEL",
    "IF",
    "SWITCH",
    "REPEAT",
    "WHILE",
    "FOREACH",
]

# Recognized keys under project.json step_config (ProjectConfig.get_step_config).
PROJECT_STEP_CONFIG_KEYS: FrozenSet[str] = frozenset(
    {
        "centroid",
        "detection",
        "mapper",
        "enricher",
        "classifier",
        "predictor",
        "alignment_qc",
        "fragmentomics",
        "validation",
        "progression",
        "cluster",
    }
)


@dataclass(frozen=True)
class DomainOutputBinding:
    """Maps worker output_json path to a field on a domain type in scope."""

    domain_type: str
    scope_field: str
    output_json_path: str


@dataclass(frozen=True)
class DomainEffects:
    reads_types: Tuple[str, ...] = ()
    writes_types: Tuple[str, ...] = ()
    scope_bindings: Tuple[Tuple[str, str], ...] = ()  # (var_name, output_json_path)
    output_bindings: Tuple[DomainOutputBinding, ...] = ()


@dataclass(frozen=True)
class ActionCatalogEntry:
    action_name: str
    capability: str
    handler: str
    schema_id: str
    description: str
    category: ActionCategory
    input_module: str
    input_class: str
    output_module: str
    output_class: str
    default_node_type: NodeType = "ACTION"
    cli_tool: Optional[str] = None
    tool: Optional[str] = None
    step_config_key: Optional[str] = None
    context_vars: Tuple[str, ...] = field(default_factory=tuple)
    domain_effects: Optional[DomainEffects] = None

    @property
    def input_schema_ref(self) -> str:
        safe = self.action_name.replace(".", "_")
        return f"schemas/tasks/{safe}.input.schema.json"

    @property
    def output_schema_ref(self) -> str:
        safe = self.action_name.replace(".", "_")
        return f"schemas/tasks/{safe}.output.schema.json"

    def to_catalog_dict(self) -> dict:
        payload = {
            "action_name": self.action_name,
            "capability": self.capability,
            "handler": self.handler,
            "schema_id": self.schema_id,
            "description": self.description,
            "category": self.category,
            "default_node_type": self.default_node_type,
            "input_schema_ref": self.input_schema_ref,
            "output_schema_ref": self.output_schema_ref,
            "step_config_key": self.step_config_key,
            "context_vars": list(self.context_vars),
        }
        if self.cli_tool:
            payload["cli_tool"] = self.cli_tool
        if self.tool:
            payload["tool"] = self.tool
        if self.domain_effects:
            de = self.domain_effects
            payload["domain_effects"] = {
                "reads_types": list(de.reads_types),
                "writes_types": list(de.writes_types),
                "scope_bindings": [
                    {"var_name": v, "output_json_path": p} for v, p in de.scope_bindings
                ],
                "output_bindings": [
                    {
                        "domain_type": b.domain_type,
                        "scope_field": b.scope_field,
                        "output_json_path": b.output_json_path,
                    }
                    for b in de.output_bindings
                ],
            }
        return payload


_PIPELINE_IN = ("methyl_worker.task_models", "PipelineCliTaskInput")
_PIPELINE_OUT = ("methyl_worker.task_models", "PipelineCliTaskOutput")
_SAMPLE_IN = ("methyl_worker.task_models", "SamplePrepTaskInput")

# Domain effect presets (see workflow_engine/contract/domain_types.md)
_DE_METHYL_SAMPLE = DomainEffects(reads_types=("MethylSampleRef",), writes_types=("MethylSampleRef",))
_DE_DOWNLOAD = DomainEffects(
    reads_types=("MethylIngestRef",),
    writes_types=("MethylSampleRef",),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "fastqFiles", "$.fastqFiles"),
    ),
)
_DE_PARABRICKS = DomainEffects(
    reads_types=("MethylSampleRef",),
    writes_types=("MethylSampleRef",),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "bamPath", "$.bamPath"),
        DomainOutputBinding("MethylSampleRef", "metricsJson", "$.metricsJson"),
    ),
)
_DE_METHYL_QC = DomainEffects(
    reads_types=("MethylSampleRef",),
    writes_types=("MethylSampleRef",),
    scope_bindings=(("qcPass", "$.guardrails.overall_pass"),),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "alignmentQc", "$.alignmentQc"),
    ),
)
_DE_FRAGMENTOMICS = DomainEffects(
    reads_types=("MethylSampleRef",),
    writes_types=("MethylSampleRef",),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "fragmentomics", "$.fragmentomics"),
    ),
)
_DE_METHYL_EXTRACT = DomainEffects(
    reads_types=("MethylSampleRef",),
    writes_types=("MethylSampleRef",),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "methylation", "$.methylation"),
    ),
)
_DE_QC_FAILED = DomainEffects(
    reads_types=("MethylSampleRef",),
    writes_types=("MethylSampleRef",),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "status", "$.status"),
    ),
)
_DE_CENTROID = DomainEffects(
    reads_types=("MethylGroup",),
    writes_types=("MethylCentroidRef",),
)
_DE_DETECTOR = DomainEffects(
    reads_types=("ComparisonSpec", "MethylCentroidRef"),
    writes_types=("MethylDetectionRef",),
)
_DE_PLAN_ITERATIONS = DomainEffects(
    reads_types=("MethylGroup",),
    writes_types=("StratifiedCohortDraw",),
    scope_bindings=(("iterations", "$.iterations"),),
)


def _entry(
    action_name: str,
    capability: str,
    handler: str,
    schema_id: str,
    description: str,
    category: ActionCategory,
    input_module: str,
    input_class: str,
    output_module: str,
    output_class: str,
    *,
    cli_tool: Optional[str] = None,
    tool: Optional[str] = None,
    step_config_key: Optional[str] = None,
    context_vars: Tuple[str, ...] = (),
    domain_effects: Optional[DomainEffects] = None,
) -> ActionCatalogEntry:
    return ActionCatalogEntry(
        action_name=action_name,
        capability=capability,
        handler=handler,
        schema_id=schema_id,
        description=description,
        category=category,
        input_module=input_module,
        input_class=input_class,
        output_module=output_module,
        output_class=output_class,
        cli_tool=cli_tool,
        tool=tool,
        step_config_key=step_config_key,
        context_vars=context_vars,
        domain_effects=domain_effects,
    )


ACTION_CATALOG: Sequence[ActionCatalogEntry] = (
    _entry(
        "pipeline.centroid",
        "methyl-centroid",
        "_handle_pipeline_cli",
        "pipeline.centroid",
        "Build per-group methylation centroids (chr×context HDF5 aggregates).",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-centroid",
        tool="MethylCentroid",
        step_config_key="centroid",
        domain_effects=_DE_CENTROID,
    ),
    _entry(
        "pipeline.detector",
        "methyl-detector",
        "_handle_pipeline_cli",
        "pipeline.detector",
        "Detect differentially methylated positions between cohort pairs.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-detector",
        tool="MethylDetector",
        step_config_key="detection",
        domain_effects=_DE_DETECTOR,
    ),
    _entry(
        "pipeline.mapper",
        "methyl-mapper",
        "_handle_pipeline_cli",
        "pipeline.mapper",
        "Map DMPs to genes and genomic features.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-mapper",
        tool="MethylMapper",
        step_config_key="mapper",
    ),
    _entry(
        "pipeline.enricher",
        "methyl-enricher",
        "_handle_pipeline_cli",
        "pipeline.enricher",
        "Functional enrichment on mapped gene sets.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-enricher",
        tool="MethylEnricher",
        step_config_key="enricher",
    ),
    _entry(
        "pipeline.progression",
        "methyl-disease-progression",
        "_handle_pipeline_cli",
        "pipeline.progression",
        "Ordered disease-stage progression analysis across comparisons.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-disease-progression",
        tool="MethylDiseaseProgression",
        step_config_key="progression",
    ),
    _entry(
        "sample.download_fastq",
        "sample.download-fastq",
        "_handle_stub_external",
        "sample.download_fastq",
        "Download sample FASTQ files from external object storage.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DownloadFastqTaskOutput",
        tool="SampleDownloadFastq",
        context_vars=("sampleId", "sampleDir", "fastqSourceUri"),
        domain_effects=_DE_DOWNLOAD,
    ),
    _entry(
        "sample.parabricks_fq2bam",
        "parabricks.fq2bam",
        "_handle_stub_external",
        "sample.parabricks_fq2bam",
        "Align FASTQs to BAM using NVIDIA Clara Parabricks fq2bam.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "ParabricksTaskOutput",
        tool="ParabricksFq2Bam",
        context_vars=("sampleId", "sampleDir", "referenceFasta", "referenceGtf"),
        domain_effects=_DE_PARABRICKS,
    ),
    _entry(
        "sample.delete_fastqs",
        "sample.delete-fastqs",
        "_handle_stub_external",
        "sample.delete_fastqs",
        "Delete FASTQ files after alignment to reclaim storage.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DeleteTaskOutput",
        tool="SampleDeleteFastqs",
        context_vars=("sampleId", "sampleDir"),
    ),
    _entry(
        "sample.methyl_qc",
        "methyl-qc",
        "_handle_methyl_qc",
        "sample.methyl_qc",
        "Alignment QC metrics (Picard-style) with guardrails JSON export.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MethylQcTaskOutput",
        cli_tool="methyl-qc",
        tool="MethylAlignmentQc",
        step_config_key="alignment_qc",
        context_vars=("projectPath", "sampleId", "sampleDir", "primaryAnalyte"),
        domain_effects=_DE_METHYL_QC,
    ),
    _entry(
        "sample.fragmentomics",
        "methyl-fragmentomics",
        "_handle_methyl_fragmentomics",
        "sample.fragmentomics",
        "cfDNA fragmentomic analysis (WPS, end motifs) when analyte is cfDNA.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "FragmentomicsTaskOutput",
        cli_tool="methyl-fragmentomics",
        tool="MethylFragmentomics",
        step_config_key="fragmentomics",
        context_vars=("projectPath", "sampleId", "sampleDir"),
        domain_effects=_DE_FRAGMENTOMICS,
    ),
    _entry(
        "sample.methyl_extract",
        "methyl-extract",
        "_handle_stub_external",
        "sample.methyl_extract",
        "Extract BAM to compressed per-chromosome HDF5 via MethylExtractor.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MethylExtractTaskOutput",
        tool="MethylExtract",
        context_vars=("sampleId", "sampleDir", "projectPath", "referenceFasta"),
        domain_effects=_DE_METHYL_EXTRACT,
    ),
    _entry(
        "sample.delete_bam",
        "sample.delete-bam",
        "_handle_stub_external",
        "sample.delete_bam",
        "Delete BAM after methylation extraction to reclaim storage.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DeleteTaskOutput",
        tool="SampleDeleteBam",
        context_vars=("sampleId", "sampleDir"),
    ),
    _entry(
        "sample.qc_failed",
        "sample.mark-failed",
        "_handle_mark_failed",
        "sample.qc_failed",
        "Mark sample QC_FAILED and skip downstream steps when guardrails fail.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MarkFailedTaskOutput",
        tool="SampleMarkFailed",
        context_vars=("sampleId", "sampleDir", "reason"),
        domain_effects=_DE_QC_FAILED,
    ),
    _entry(
        "validation.plan_iterations",
        "validation.plan-iterations",
        "_handle_validation_plan_iterations",
        "validation.plan_iterations",
        "Monte Carlo planner: stratified per-cohort subsamples and materialize run projects.",
        "validation",
        "methyl_validation.workflow_planner",
        "ValidationPlanRequest",
        "methyl_worker.task_models",
        "ValidationPlanTaskOutput",
        step_config_key="validation",
        context_vars=("projectPath", "featureIterations", "qualityIterations"),
        domain_effects=_DE_PLAN_ITERATIONS,
    ),
)


def list_action_catalog() -> List[ActionCatalogEntry]:
    return list(ACTION_CATALOG)


def find_catalog_entry(action_name: str) -> Optional[ActionCatalogEntry]:
    for entry in ACTION_CATALOG:
        if entry.action_name == action_name:
            return entry
    return None


def find_catalog_entry_by_capability(capability: str) -> Optional[ActionCatalogEntry]:
    for entry in ACTION_CATALOG:
        if entry.capability == capability:
            return entry
    return None


def build_capability_handlers() -> Dict[str, str]:
    return {entry.capability: entry.handler for entry in ACTION_CATALOG}


def build_tool_cli_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for entry in ACTION_CATALOG:
        if entry.tool and entry.cli_tool:
            mapping[entry.tool] = entry.cli_tool
    return mapping


def validate_catalog_linkage() -> List[str]:
    """Ensure every catalog entry maps to step_config or declares context_vars."""
    errors: List[str] = []
    for entry in ACTION_CATALOG:
        if entry.step_config_key is not None:
            if entry.step_config_key not in PROJECT_STEP_CONFIG_KEYS:
                errors.append(
                    f"{entry.action_name}: unknown step_config_key {entry.step_config_key!r}"
                )
        elif not entry.context_vars:
            errors.append(
                f"{entry.action_name}: must set step_config_key or non-empty context_vars"
            )
    return errors
