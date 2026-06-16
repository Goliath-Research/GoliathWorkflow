"""
Unified catalog of all workflow ACTION definitions.

Single source of truth for action_name, capability, handler dispatch, CLI/tool
mapping, task I/O schema models, and project.json step_config linkage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Literal, Mapping, Optional, Sequence, Tuple, TypedDict

if TYPE_CHECKING:
    from .actions.base import ActionBase

ExecutionMode = Literal["cli", "in_process"]
ActionCategory = Literal["sample_prep", "modeling", "validation"]
StepConfigKey = Literal[
    "centroid",
    "detection",
    "mapper",
    "enricher",
    "classifier",
    "predictor",
    "alignment_qc",
    "fragmentomics",
    "methyl_extract",
    "validation",
    "progression",
    "cluster",
]
ArgvMap = Tuple[Tuple[str, str], ...]
ContextVars = Tuple[str, ...]
SchemaRef = Tuple[str, str]  # (module, class)

DEFAULT_PIPELINE_ARGV_MAP: ArgvMap = (
    ("project", "--project"),
    ("projectPath", "--project"),
    ("group", "--group"),
    ("chromosome", "--chromosome"),
    ("context", "--context"),
    ("comparison", "--comparison"),
    ("outputDir", "--output-dir"),
    ("centroid1Dir", "--centroid1-dir"),
    ("centroid2Dir", "--centroid2-dir"),
    ("stepOverride", "--step-override"),
)
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
PROJECT_STEP_CONFIG_KEYS: FrozenSet[StepConfigKey] = frozenset(
    {
        "centroid",
        "detection",
        "mapper",
        "enricher",
        "classifier",
        "predictor",
        "alignment_qc",
        "fragmentomics",
        "methyl_extract",
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


class ActionCatalogExport(TypedDict, total=False):
    action_name: str
    capability: str
    execution_mode: ExecutionMode
    schema_id: str
    description: str
    category: ActionCategory
    default_node_type: NodeType
    input_schema_ref: str
    output_schema_ref: str
    step_config_key: StepConfigKey
    context_vars: List[str]
    argv_map: Dict[str, str]
    in_process_handler: str
    cli_tool: str
    tool: str
    domain_effects: Dict[str, Any]


@dataclass(frozen=True)
class ActionCatalogEntry:
    action_name: str
    capability: str
    schema_id: str
    description: str
    category: ActionCategory
    input_module: str
    input_class: str
    output_module: str
    output_class: str
    execution_mode: ExecutionMode = "cli"
    default_node_type: NodeType = "ACTION"
    cli_tool: Optional[str] = None
    tool: Optional[str] = None
    step_config_key: Optional[StepConfigKey] = None
    context_vars: ContextVars = field(default_factory=tuple)
    argv_map: ArgvMap = DEFAULT_PIPELINE_ARGV_MAP
    in_process_handler: Optional[str] = None
    handler: Optional[str] = None  # deprecated alias for in_process_handler
    domain_effects: Optional[DomainEffects] = None

    def __post_init__(self) -> None:
        errors = list(_entry_invariant_errors(self))
        if errors:
            raise ValueError("; ".join(errors))

    def resolved_in_process_handler(self) -> Optional[str]:
        return self.in_process_handler or self.handler

    def build_action(self, handlers_module: Any = None) -> ActionBase:
        from .actions.base import build_action_from_catalog
        import methyl_worker.handlers as handlers_mod

        mod = handlers_module if handlers_module is not None else handlers_mod
        return build_action_from_catalog(self, mod)

    @property
    def input_schema_ref(self) -> str:
        safe = self.action_name.replace(".", "_")
        return f"schemas/tasks/{safe}.input.schema.json"

    @property
    def output_schema_ref(self) -> str:
        safe = self.action_name.replace(".", "_")
        return f"schemas/tasks/{safe}.output.schema.json"

    def to_catalog_dict(self) -> ActionCatalogExport:
        payload: ActionCatalogExport = {
            "action_name": self.action_name,
            "capability": self.capability,
            "execution_mode": self.execution_mode,
            "schema_id": self.schema_id,
            "description": self.description,
            "category": self.category,
            "default_node_type": self.default_node_type,
            "input_schema_ref": self.input_schema_ref,
            "output_schema_ref": self.output_schema_ref,
            "context_vars": list(self.context_vars),
            "argv_map": {k: v for k, v in self.argv_map},
        }
        if self.step_config_key is not None:
            payload["step_config_key"] = self.step_config_key
        handler = self.resolved_in_process_handler()
        if handler:
            payload["in_process_handler"] = handler
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


_PIPELINE_IN: SchemaRef = ("methyl_worker.task_models", "PipelineCliTaskInput")
_PIPELINE_OUT: SchemaRef = ("methyl_worker.task_models", "PipelineCliTaskOutput")
_SAMPLE_IN: SchemaRef = ("methyl_worker.task_models", "SamplePrepTaskInput")

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
        DomainOutputBinding("MethylSampleRef", "qcMetricsTar", "$.qcMetricsTar"),
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
_DE_PREPARE_FREEZE = DomainEffects(
    reads_types=("StratifiedCohortDraw",),
    writes_types=("ValidationArtifactRef",),
    scope_bindings=(("fixedDmpPanel", "$.fixedDmpPanel"),),
)
_DE_SELECT_BEST_MODEL = DomainEffects(
    reads_types=("StratifiedCohortDraw",),
    writes_types=("ValidationArtifactRef",),
    scope_bindings=(("selectedBackend", "$.selectedBackend"),),
)
_DE_VALIDATION = DomainEffects(
    reads_types=("StratifiedCohortDraw",),
    writes_types=("ValidationArtifactRef",),
)


def _entry_invariant_errors(entry: ActionCatalogEntry) -> List[str]:
    """Cross-field catalog rules enforced at construction and by validate_catalog()."""
    errors: List[str] = []
    if entry.execution_mode == "cli":
        if not entry.cli_tool:
            errors.append(f"{entry.action_name}: cli actions require cli_tool")
    elif entry.execution_mode == "in_process":
        if not entry.resolved_in_process_handler():
            errors.append(f"{entry.action_name}: in_process actions require in_process_handler")
    else:
        errors.append(f"{entry.action_name}: unknown execution_mode {entry.execution_mode!r}")

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


def _entry(
    action_name: str,
    capability: str,
    schema_id: str,
    description: str,
    category: ActionCategory,
    input_module: str,
    input_class: str,
    output_module: str,
    output_class: str,
    *,
    execution_mode: ExecutionMode = "cli",
    cli_tool: Optional[str] = None,
    tool: Optional[str] = None,
    step_config_key: Optional[StepConfigKey] = None,
    context_vars: ContextVars = (),
    argv_map: ArgvMap = DEFAULT_PIPELINE_ARGV_MAP,
    in_process_handler: Optional[str] = None,
    domain_effects: Optional[DomainEffects] = None,
) -> ActionCatalogEntry:
    return ActionCatalogEntry(
        action_name=action_name,
        capability=capability,
        schema_id=schema_id,
        description=description,
        category=category,
        input_module=input_module,
        input_class=input_class,
        output_module=output_module,
        output_class=output_class,
        execution_mode=execution_mode,
        cli_tool=cli_tool,
        tool=tool,
        step_config_key=step_config_key,
        context_vars=context_vars,
        argv_map=argv_map,
        in_process_handler=in_process_handler,
        domain_effects=domain_effects,
    )


def _cli(
    action_name: str,
    capability: str,
    schema_id: str,
    description: str,
    category: ActionCategory,
    input_module: str,
    input_class: str,
    output_module: str,
    output_class: str,
    *,
    cli_tool: str,
    tool: Optional[str] = None,
    step_config_key: Optional[StepConfigKey] = None,
    context_vars: ContextVars = (),
    argv_map: ArgvMap = DEFAULT_PIPELINE_ARGV_MAP,
    domain_effects: Optional[DomainEffects] = None,
) -> ActionCatalogEntry:
    return _entry(
        action_name,
        capability,
        schema_id,
        description,
        category,
        input_module,
        input_class,
        output_module,
        output_class,
        execution_mode="cli",
        cli_tool=cli_tool,
        tool=tool,
        step_config_key=step_config_key,
        context_vars=context_vars,
        argv_map=argv_map,
        domain_effects=domain_effects,
    )


def _in_process(
    action_name: str,
    capability: str,
    schema_id: str,
    description: str,
    category: ActionCategory,
    input_module: str,
    input_class: str,
    output_module: str,
    output_class: str,
    *,
    in_process_handler: str,
    tool: Optional[str] = None,
    cli_tool: Optional[str] = None,
    step_config_key: Optional[StepConfigKey] = None,
    context_vars: ContextVars = (),
    domain_effects: Optional[DomainEffects] = None,
) -> ActionCatalogEntry:
    return _entry(
        action_name,
        capability,
        schema_id,
        description,
        category,
        input_module,
        input_class,
        output_module,
        output_class,
        execution_mode="in_process",
        in_process_handler=in_process_handler,
        tool=tool,
        cli_tool=cli_tool,
        step_config_key=step_config_key,
        context_vars=context_vars,
        argv_map=(),
        domain_effects=domain_effects,
    )


ACTION_CATALOG: Sequence[ActionCatalogEntry] = (
    _cli(
        "pipeline.centroid",
        "methyl-centroid",
        "pipeline.centroid",
        "Build per-group methylation centroids (chr×context HDF5 aggregates).",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-centroid",
        tool="MethylCentroid",
        step_config_key="centroid",
        context_vars=("group", "chromosome", "context", "outputDir", "addSamples", "removeSamples", "stepOverride"),
        argv_map=DEFAULT_PIPELINE_ARGV_MAP,
        domain_effects=_DE_CENTROID,
    ),
    _cli(
        "pipeline.detector",
        "methyl-detector",
        "pipeline.detector",
        "Detect differentially methylated positions between cohort pairs.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-detector",
        tool="MethylDetector",
        step_config_key="detection",
        context_vars=("chromosome", "context", "comparison", "fixedDmpPanel", "stepOverride"),
        argv_map=DEFAULT_PIPELINE_ARGV_MAP,
        domain_effects=_DE_DETECTOR,
    ),
    _cli(
        "pipeline.mapper",
        "methyl-mapper",
        "pipeline.mapper",
        "Map DMPs to genes and genomic features.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-mapper",
        tool="MethylMapper",
        step_config_key="mapper",
    ),
    _cli(
        "pipeline.enricher",
        "methyl-enricher",
        "pipeline.enricher",
        "Functional enrichment on mapped gene sets.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-enricher",
        tool="MethylEnricher",
        step_config_key="enricher",
    ),
    _cli(
        "pipeline.progression",
        "methyl-disease-progression",
        "pipeline.progression",
        "Ordered disease-stage progression analysis across comparisons.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-disease-progression",
        tool="MethylDiseaseProgression",
        step_config_key="progression",
    ),
    _cli(
        "pipeline.classifier",
        "methyl-classifier",
        "pipeline.classifier",
        "Train production classifier from frozen centroids and DMP panel.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-classifier",
        tool="MethylClassifier",
        step_config_key="classifier",
    ),
    _cli(
        "pipeline.predictor",
        "methyl-predictor",
        "pipeline.predictor",
        "Run predictor on holdout samples using trained classifier.",
        "modeling",
        *_PIPELINE_IN,
        *_PIPELINE_OUT,
        cli_tool="methyl-predictor",
        tool="MethylPredictor",
        step_config_key="predictor",
    ),
    _in_process(
        "sample.download_fastq",
        "sample.download-fastq",
        "sample.download_fastq",
        "Download sample FASTQ files from external object storage.",
        "sample_prep",
        "methyl_worker.task_models",
        "DownloadFastqTaskInput",
        "methyl_worker.task_models",
        "DownloadFastqTaskOutput",
        in_process_handler="_handle_download_fastq",
        tool="SampleDownloadFastq",
        context_vars=("sampleId", "sampleDir", "fastqSourceUri"),
        domain_effects=_DE_DOWNLOAD,
    ),
    _in_process(
        "sample.parabricks_fq2bam",
        "parabricks.fq2bam",
        "sample.parabricks_fq2bam",
        "Align bisulfite FASTQs to BAM using NVIDIA Clara Parabricks fq2bam_meth (Docker).",
        "sample_prep",
        "methyl_worker.task_models",
        "ParabricksFq2bamTaskInput",
        "methyl_worker.task_models",
        "ParabricksTaskOutput",
        in_process_handler="_handle_parabricks_fq2bam",
        tool="ParabricksFq2Bam",
        context_vars=("sampleId", "sampleDir", "referenceFasta", "referenceGtf"),
        domain_effects=_DE_PARABRICKS,
    ),
    _in_process(
        "sample.delete_fastqs",
        "sample.delete-fastqs",
        "sample.delete_fastqs",
        "Delete FASTQ files after alignment to reclaim storage.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DeleteTaskOutput",
        in_process_handler="_handle_delete_fastqs",
        tool="SampleDeleteFastqs",
        context_vars=("sampleId", "sampleDir"),
    ),
    _in_process(
        "sample.methyl_qc",
        "methyl-qc",
        "sample.methyl_qc",
        "Alignment QC metrics (Picard-style) with guardrails JSON export.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MethylQcTaskOutput",
        in_process_handler="_handle_methyl_qc",
        tool="MethylAlignmentQc",
        cli_tool="methyl-qc",
        step_config_key="alignment_qc",
        context_vars=("projectPath", "sampleId", "sampleDir", "primaryAnalyte"),
        domain_effects=_DE_METHYL_QC,
    ),
    _in_process(
        "sample.fragmentomics",
        "methyl-fragmentomics",
        "sample.fragmentomics",
        "cfDNA fragmentomic analysis (WPS, end motifs) when analyte is cfDNA.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "FragmentomicsTaskOutput",
        in_process_handler="_handle_methyl_fragmentomics",
        tool="MethylFragmentomics",
        cli_tool="methyl-fragmentomics",
        step_config_key="fragmentomics",
        context_vars=("projectPath", "sampleId", "sampleDir"),
        domain_effects=_DE_FRAGMENTOMICS,
    ),
    _in_process(
        "sample.methyl_extract",
        "methyl-extract",
        "sample.methyl_extract",
        "Extract BAM to per-chromosome HDF5 via native MethylExtractor (config from project step_config.methyl_extract).",
        "sample_prep",
        "methyl_worker.task_models",
        "MethylExtractTaskInput",
        "methyl_worker.task_models",
        "MethylExtractTaskOutput",
        in_process_handler="_handle_methyl_extract",
        tool="MethylExtract",
        step_config_key="methyl_extract",
        context_vars=("sampleId", "sampleDir", "projectPath", "referenceFasta"),
        domain_effects=_DE_METHYL_EXTRACT,
    ),
    _in_process(
        "sample.delete_bam",
        "sample.delete-bam",
        "sample.delete_bam",
        "Delete BAM after methylation extraction to reclaim storage.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "DeleteTaskOutput",
        in_process_handler="_handle_delete_bam",
        tool="SampleDeleteBam",
        context_vars=("sampleId", "sampleDir"),
    ),
    _in_process(
        "sample.qc_failed",
        "sample.mark-failed",
        "sample.qc_failed",
        "Mark sample QC_FAILED and skip downstream steps when guardrails fail.",
        "sample_prep",
        _SAMPLE_IN[0],
        _SAMPLE_IN[1],
        "methyl_worker.task_models",
        "MarkFailedTaskOutput",
        in_process_handler="_handle_mark_failed",
        tool="SampleMarkFailed",
        context_vars=("sampleId", "sampleDir", "reason"),
        domain_effects=_DE_QC_FAILED,
    ),
    _in_process(
        "validation.plan_iterations",
        "validation.plan-iterations",
        "validation.plan_iterations",
        "Monte Carlo planner: stratified per-cohort subsamples and materialize run projects.",
        "validation",
        "methyl_validation.workflow_planner",
        "ValidationPlanRequest",
        "methyl_worker.task_models",
        "ValidationPlanTaskOutput",
        in_process_handler="_handle_validation_plan_iterations",
        step_config_key="validation",
        context_vars=("projectPath", "featureIterations", "qualityIterations"),
        domain_effects=_DE_PLAN_ITERATIONS,
    ),
    _in_process(
        "validation.stability",
        "validation.stability",
        "validation.stability",
        "Aggregate Monte Carlo DMP/gene stability and write production-ready panels.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_stability",
        step_config_key="validation",
        context_vars=("projectPath", "monteCarloRunsRoot", "outputDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.prepare_freeze_project",
        "validation.prepare-freeze-project",
        "validation.prepare_freeze_project",
        "Write production/project.json with fixed_dmp_panel for granular freeze workflows.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_prepare_freeze",
        step_config_key="validation",
        context_vars=("projectPath", "stableDmpCsv", "productionOutputDir"),
        domain_effects=_DE_PREPARE_FREEZE,
    ),
    _in_process(
        "validation.stability_freeze_readiness",
        "validation.stability-freeze-readiness",
        "validation.stability_freeze_readiness",
        "Audit stability, freeze, and progression artifacts before model training.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_stability_freeze_readiness",
        step_config_key="validation",
        context_vars=("projectPath",),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.link_artifacts",
        "validation.link-artifacts",
        "validation.link_artifacts",
        "Symlink centroids/detections from a source MC run into a model-mc iteration dir.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_link_artifacts",
        context_vars=("sourceRunDir", "targetRunDir", "runDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.model_bundle",
        "validation.model-bundle",
        "validation.model_bundle",
        "Build model feature bundle (tabular/generative) from frozen detections.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_model_bundle",
        context_vars=("projectPath", "bundleDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.model_train",
        "validation.model-train",
        "validation.model_train",
        "Train tabular or generative backend model for one MC model iteration.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_model_train",
        context_vars=("projectPath", "backend", "runDir", "bundleH5", "outputDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.model_predict",
        "validation.model-predict",
        "validation.model_predict",
        "Predict with tabular or generative backend for one MC model iteration.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_model_predict",
        context_vars=("projectPath", "backend", "runDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.select_best_model",
        "validation.select-best-model",
        "validation.select_best_model",
        "Rank model-mc backends and build final production model on all data.",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_select_best_model",
        step_config_key="validation",
        context_vars=("projectPath", "modelMcRoot", "backends", "selectionMetric", "selectionStat"),
        domain_effects=_DE_SELECT_BEST_MODEL,
    ),
    _in_process(
        "validation.model_mc",
        "validation.model-mc",
        "validation.model_mc",
        "Monte Carlo model training across backends (shared centroid/detector + per-backend model loops).",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_model_mc",
        step_config_key="validation",
        context_vars=("projectPath", "monteCarloRunsRoot", "backends", "productionOutputDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.post_model_validation",
        "validation.post-model-validation",
        "validation.post_model_validation",
        "Holdout evaluation with frozen production artifacts (predictor-only / frozen inference).",
        "validation",
        "methyl_worker.task_models",
        "ValidationTaskInput",
        "methyl_worker.task_models",
        "ValidationTaskOutput",
        in_process_handler="_handle_validation_post_model_validation",
        step_config_key="validation",
        context_vars=("projectPath", "runDir", "productionOutputDir"),
        domain_effects=_DE_VALIDATION,
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
    """Map capability to in-process handler name (cli actions have no handler)."""
    mapping: Dict[str, str] = {}
    for entry in ACTION_CATALOG:
        handler = entry.resolved_in_process_handler()
        if handler:
            mapping[entry.capability] = handler
    return mapping


def build_tool_cli_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for entry in ACTION_CATALOG:
        if entry.tool and entry.cli_tool:
            mapping[entry.tool] = entry.cli_tool
    return mapping


def validate_catalog() -> List[str]:
    """Return all invariant violations across ACTION_CATALOG."""
    errors: List[str] = []
    for entry in ACTION_CATALOG:
        errors.extend(_entry_invariant_errors(entry))
    return errors


def validate_catalog_linkage() -> List[str]:
    """Backward-compatible alias for validate_catalog()."""
    return validate_catalog()
