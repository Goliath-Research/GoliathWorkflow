"""
Unified catalog of all workflow ACTION definitions.

Single source of truth for action_name, capability, handler dispatch, CLI/tool
mapping, and task I/O schema models. Tool parameters resolve via profile/site
``actionConfig`` into task ``resolvedConfig`` (not study manifest step_config).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Literal, Mapping, Optional, Sequence, Tuple, TypedDict

if TYPE_CHECKING:
    from .actions.base import ActionBase

ExecutionMode = Literal["cli", "in_process"]
ActionCategory = Literal["sample_prep", "modeling", "validation"]
ActionConfigKey = Literal[
    "centroid",
    "detection",
    "dmp_selection",
    "mapper",
    "enricher",
    "classifier",
    "gene_selection",
    "predictor",
    "alignment_qc",
    "extraction_qc",
    "fragmentomics",
    "methyl_extract",
    "validation",
    "progression",
    "parabricks",
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
    ("resolvedConfigPath", "--resolved-config"),
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

# Recognized action catalog keys resolved via action_config_resolver.
PROJECT_ACTION_CONFIG_KEYS: FrozenSet[ActionConfigKey] = frozenset(
    {
        "centroid",
        "detection",
        "dmp_selection",
        "mapper",
        "enricher",
        "classifier",
        "gene_selection",
        "predictor",
        "alignment_qc",
        "extraction_qc",
        "fragmentomics",
        "methyl_extract",
        "validation",
        "progression",
        "parabricks",
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
    action_config_key: ActionConfigKey
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
    action_config_key: Optional[ActionConfigKey] = None
    context_vars: ContextVars = field(default_factory=tuple)
    argv_map: ArgvMap = DEFAULT_PIPELINE_ARGV_MAP
    in_process_handler: Optional[str] = None
    handler: Optional[str] = None  # deprecated alias for in_process_handler
    idempotency_enabled: bool = False
    internal: bool = False
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
        if self.action_config_key is not None:
            payload["action_config_key"] = self.action_config_key
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


_PIPELINE_MODULE = "methyl_worker.task_models.pipeline_models"
_SAMPLE_MODULE = "methyl_worker.task_models.sample_prep_models"
_VALIDATION_MODULE = "methyl_worker.task_models.validation_models"
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
    scope_bindings=(
        ("qcPass", "$.guardrails.overall_pass"),
        ("qcDisposition", "$.screening.disposition"),
        ("trimFront1", "$.screening.trim_front1"),
        ("trimTail1", "$.screening.trim_tail1"),
        ("trimFront2", "$.screening.trim_front2"),
        ("trimTail2", "$.screening.trim_tail2"),
        ("qcAttemptReason", "$.screening.message"),
        ("remediateAlignment", "$.remediateAlignment"),
        ("remediateR2Trim", "$.remediateR2Trim"),
    ),
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
_DE_EXTRACTION_QC = DomainEffects(
    reads_types=("MethylSampleRef",),
    writes_types=("MethylSampleRef",),
    scope_bindings=(
        ("extractionQcPass", "$.guardrails.overall_pass"),
    ),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "extractionQc", "$.extractionQc"),
    ),
)
_DE_ARCHIVE_SAMPLE = DomainEffects(
    reads_types=("MethylSampleRef",),
    writes_types=("MethylSampleRef",),
    scope_bindings=(("sampleArchived", "$.sampleArchived"),),
    output_bindings=(
        DomainOutputBinding("MethylSampleRef", "sampleArchive", "$.sampleArchive"),
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
    writes_types=("StratifiedCohortDraw", "CentroidSeedGroup"),
    scope_bindings=(
        ("iterations", "$.iterations"),
        ("centroidSeedGroups", "$.centroidSeedGroups"),
    ),
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
_DE_RESOLVE_PROJECT = DomainEffects(
    reads_types=("MethylGroup", "ComparisonSpec"),
    writes_types=("ResolvedProject",),
    scope_bindings=(("resolvedProject", "$.resolvedProject"),),
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

    if entry.action_config_key is not None:
        if entry.action_config_key not in PROJECT_ACTION_CONFIG_KEYS:
            errors.append(
                f"{entry.action_name}: unknown action_config_key {entry.action_config_key!r}"
            )
    elif not entry.context_vars:
        errors.append(
            f"{entry.action_name}: must set action_config_key or non-empty context_vars"
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
    action_config_key: Optional[ActionConfigKey] = None,
    context_vars: ContextVars = (),
    argv_map: ArgvMap = DEFAULT_PIPELINE_ARGV_MAP,
    in_process_handler: Optional[str] = None,
    idempotency_enabled: bool = False,
    domain_effects: Optional[DomainEffects] = None,
    internal: bool = False,
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
        action_config_key=action_config_key,
        context_vars=context_vars,
        argv_map=argv_map,
        in_process_handler=in_process_handler,
        idempotency_enabled=idempotency_enabled,
        domain_effects=domain_effects,
        internal=internal,
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
    action_config_key: Optional[ActionConfigKey] = None,
    context_vars: ContextVars = (),
    argv_map: ArgvMap = DEFAULT_PIPELINE_ARGV_MAP,
    domain_effects: Optional[DomainEffects] = None,
    idempotency_enabled: bool = False,
    internal: bool = False,
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
        action_config_key=action_config_key,
        context_vars=context_vars,
        argv_map=argv_map,
        domain_effects=domain_effects,
        idempotency_enabled=idempotency_enabled,
        internal=internal,
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
    action_config_key: Optional[ActionConfigKey] = None,
    context_vars: ContextVars = (),
    domain_effects: Optional[DomainEffects] = None,
    idempotency_enabled: bool = False,
    internal: bool = False,
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
        action_config_key=action_config_key,
        context_vars=context_vars,
        argv_map=(),
        domain_effects=domain_effects,
        idempotency_enabled=idempotency_enabled,
        internal=internal,
    )


ACTION_CATALOG: Sequence[ActionCatalogEntry] = (
    _cli(
        "pipeline.centroid",
        "methyl-centroid",
        "pipeline.centroid",
        "Build per-group methylation centroids (chr×context HDF5 aggregates).",
        "modeling",
        _PIPELINE_MODULE,
        "CentroidTaskInput",
        _PIPELINE_MODULE,
        "CentroidTaskOutput",
        cli_tool="methyl-centroid",
        tool="MethylCentroid",
        action_config_key="centroid",
        context_vars=("group", "chromosome", "context", "outputDir", "stepOverride", "addSamples", "removeSamples", "centroidSeedDir"),
        argv_map=DEFAULT_PIPELINE_ARGV_MAP,
        domain_effects=_DE_CENTROID,
    ),
    _cli(
        "pipeline.detector",
        "methyl-detector",
        "pipeline.detector",
        "Detect differentially methylated positions between cohort pairs.",
        "modeling",
        _PIPELINE_MODULE,
        "DetectorTaskInput",
        _PIPELINE_MODULE,
        "DetectorTaskOutput",
        cli_tool="methyl-detector",
        tool="MethylDetector",
        action_config_key="detection",
        context_vars=("chromosome", "context", "comparison", "fixedDmpPanel", "stepOverride"),
        argv_map=(
            ("project", "--project"),
            ("projectPath", "--project"),
            ("group", "--group"),
            ("centroid1Dir", "--centroid1-dir"),
            ("centroid2Dir", "--centroid2-dir"),
            ("stepOverride", "--step-override"),
        ),
        domain_effects=_DE_DETECTOR,
    ),
    _cli(
        "pipeline.dmp_select",
        "methyl-dmp-select",
        "pipeline.dmp_select",
        "Select minimal discriminatory DMP panel from discovery exports (FeatureCuts / elbow).",
        "modeling",
        _PIPELINE_MODULE,
        "DmpSelectTaskInput",
        _PIPELINE_MODULE,
        "DmpSelectTaskOutput",
        cli_tool="methyl-dmp-select",
        tool="MethylDmpSelect",
        action_config_key="dmp_selection",
        context_vars=("chromosome", "context", "comparison", "discoveryCsv", "outputDir", "stepOverride"),
        argv_map=(
            ("project", "--project"),
            ("projectPath", "--project"),
            ("group", "--group"),
            ("chromosome", "--chromosome"),
            ("discoveryCsv", "--discovery-csv"),
            ("outputDir", "--output-dir"),
            ("stepOverride", "--step-override"),
        ),
        domain_effects=_DE_DETECTOR,
    ),
    _cli(
        "pipeline.mapper",
        "methyl-mapper",
        "pipeline.mapper",
        "Map DMPs to genes and genomic features.",
        "modeling",
        _PIPELINE_MODULE,
        "MapperTaskInput",
        _PIPELINE_MODULE,
        "MapperTaskOutput",
        cli_tool="methyl-mapper",
        tool="MethylMapper",
        action_config_key="mapper",
    ),
    _cli(
        "pipeline.gene_select",
        "methyl-gene-select",
        "pipeline.gene_select",
        "Validation-driven gene panel selection (ECDF OvR FeatureCuts).",
        "modeling",
        _PIPELINE_MODULE,
        "GeneSelectTaskInput",
        _PIPELINE_MODULE,
        "GeneSelectTaskOutput",
        cli_tool="methyl-gene-select",
        tool="MethylGeneSelect",
        action_config_key="gene_selection",
        context_vars=("comparison", "runDir", "biomarkerFilter"),
        argv_map=(
            ("project", "--project"),
            ("projectPath", "--project"),
            ("runDir", "--run-dir"),
            ("biomarkerFilter", "--biomarker-filter"),
        ),
    ),
    _cli(
        "pipeline.gene_feature_select",
        "methyl-gene-feature-select",
        "pipeline.gene_feature_select",
        "Select structural gene × region features for tabular structural_scored backends.",
        "modeling",
        _PIPELINE_MODULE,
        "GeneFeatureSelectTaskInput",
        _PIPELINE_MODULE,
        "GeneFeatureSelectTaskOutput",
        cli_tool="methyl-gene-feature-select",
        tool="MethylGeneFeatureSelect",
        action_config_key="gene_selection",
        context_vars=("mapperDir", "outputDir"),
        argv_map=(
            ("mapperDir", "--mapper-dir"),
            ("outputDir", "--output-dir"),
        ),
    ),
    _cli(
        "pipeline.enricher",
        "methyl-enricher",
        "pipeline.enricher",
        "Functional enrichment on mapped gene sets.",
        "modeling",
        _PIPELINE_MODULE,
        "EnricherTaskInput",
        _PIPELINE_MODULE,
        "EnricherTaskOutput",
        cli_tool="methyl-enricher",
        tool="MethylEnricher",
        action_config_key="enricher",
    ),
    _cli(
        "pipeline.progression",
        "methyl-disease-progression",
        "pipeline.progression",
        "Ordered disease-stage progression analysis across comparisons.",
        "modeling",
        _PIPELINE_MODULE,
        "ProgressionTaskInput",
        _PIPELINE_MODULE,
        "ProgressionTaskOutput",
        cli_tool="methyl-disease-progression",
        tool="MethylDiseaseProgression",
        action_config_key="progression",
    ),
    _cli(
        "pipeline.classifier",
        "methyl-classifier",
        "pipeline.classifier",
        "Train production classifier from frozen centroids and DMP panel.",
        "modeling",
        _PIPELINE_MODULE,
        "ClassifierTaskInput",
        _PIPELINE_MODULE,
        "ClassifierTaskOutput",
        cli_tool="methyl-classifier",
        tool="MethylClassifier",
        action_config_key="classifier",
    ),
    _cli(
        "pipeline.predictor",
        "methyl-predictor",
        "pipeline.predictor",
        "Run predictor on holdout samples using trained classifier.",
        "modeling",
        _PIPELINE_MODULE,
        "PredictorTaskInput",
        _PIPELINE_MODULE,
        "PredictorTaskOutput",
        cli_tool="methyl-predictor",
        tool="MethylPredictor",
        action_config_key="predictor",
    ),
    _in_process(
        "context.resolve_project",
        "context.resolve-project",
        "context.resolve_project",
        "Materialize study manifest paths and cohorts into a typed ResolvedProject.",
        "validation",
        "methyl_worker.task_models.context_models",
        "ResolveProjectTaskInput",
        "methyl_worker.task_models.context_models",
        "ResolveProjectTaskOutput",
        in_process_handler="_handle_context_resolve_project",
        tool="ContextResolveProject",
        context_vars=("projectPath", "monteCarloRunsRoot", "cohortPathsList"),
        domain_effects=_DE_RESOLVE_PROJECT,
    ),
    _in_process(
        "sample.download_fastq",
        "sample.download-fastq",
        "sample.download_fastq",
        "Download sample FASTQ files from external object storage.",
        "sample_prep",
        _SAMPLE_MODULE,
        "DownloadFastqTaskInput",
        _SAMPLE_MODULE,
        "DownloadFastqTaskOutput",
        in_process_handler="_handle_download_fastq",
        tool="SampleDownloadFastq",
        context_vars=("sampleId", "sampleDir", "fastqSource"),
        domain_effects=_DE_DOWNLOAD,
    ),
    _in_process(
        "sample.parabricks_fq2bam",
        "parabricks.fq2bam",
        "sample.parabricks_fq2bam",
        "Align bisulfite FASTQs to BAM using NVIDIA Clara Parabricks fq2bam_meth (Docker).",
        "sample_prep",
        _SAMPLE_MODULE,
        "ParabricksFq2bamTaskInput",
        _SAMPLE_MODULE,
        "ParabricksTaskOutput",
        in_process_handler="_handle_parabricks_fq2bam",
        tool="ParabricksFq2Bam",
        context_vars=("sampleId", "sampleDir", "projectPath"),
        domain_effects=_DE_PARABRICKS,
        action_config_key="parabricks",
    ),
    _in_process(
        "sample.parabricks_giraffe",
        "parabricks.giraffe",
        "sample.parabricks_giraffe",
        "Align FASTQs with Parabricks vg Giraffe (HPRC pangenome, GRCh38 surjection) + collectmultiplemetrics QC.",
        "sample_prep",
        _SAMPLE_MODULE,
        "ParabricksGiraffeTaskInput",
        _SAMPLE_MODULE,
        "ParabricksTaskOutput",
        in_process_handler="_handle_parabricks_giraffe",
        tool="ParabricksGiraffe",
        context_vars=("sampleId", "sampleDir", "projectPath"),
        domain_effects=_DE_PARABRICKS,
        action_config_key="parabricks",
    ),
    _in_process(
        "sample.delete_fastqs",
        "sample.delete-fastqs",
        "sample.delete_fastqs",
        "Delete FASTQ files after final QC (pass or final fail) to reclaim storage.",
        "sample_prep",
        _SAMPLE_MODULE,
        "DeleteFastqsTaskInput",
        _SAMPLE_MODULE,
        "DeleteTaskOutput",
        in_process_handler="_handle_delete_fastqs",
        tool="SampleDeleteFastqs",
        context_vars=("sampleId", "sampleDir"),
    ),
    _in_process(
        "sample.trim_fastq",
        "sample.trim-fastq",
        "sample.trim_fastq",
        "Trim Read 1/2 start or end bases with fastp before forced realign.",
        "sample_prep",
        _SAMPLE_MODULE,
        "TrimFastqTaskInput",
        _SAMPLE_MODULE,
        "TrimFastqTaskOutput",
        in_process_handler="_handle_trim_fastq",
        tool="SampleTrimFastq",
        context_vars=(
            "sampleId",
            "sampleDir",
            "trimFront1",
            "trimTail1",
            "trimFront2",
            "trimTail2",
            "remediationReason",
        ),
    ),
    _in_process(
        "sample.methyl_qc",
        "methyl-qc",
        "sample.methyl_qc",
        "Alignment QC metrics (Picard-style) with guardrails JSON export.",
        "sample_prep",
        _SAMPLE_MODULE,
        "MethylQcTaskInput",
        _SAMPLE_MODULE,
        "MethylQcTaskOutput",
        in_process_handler="_handle_methyl_qc",
        tool="MethylAlignmentQc",
        cli_tool="methyl-qc",
        action_config_key="alignment_qc",
        context_vars=("projectPath", "sampleId", "sampleDir", "primaryAnalyte"),
        domain_effects=_DE_METHYL_QC,
    ),
    _in_process(
        "sample.fragmentomics",
        "methyl-fragmentomics",
        "sample.fragmentomics",
        "cfDNA fragmentomic analysis (WPS, end motifs) when analyte is cfDNA.",
        "sample_prep",
        _SAMPLE_MODULE,
        "FragmentomicsTaskInput",
        _SAMPLE_MODULE,
        "FragmentomicsTaskOutput",
        in_process_handler="_handle_methyl_fragmentomics",
        tool="MethylFragmentomics",
        cli_tool="methyl-fragmentomics",
        action_config_key="fragmentomics",
        context_vars=("projectPath", "sampleId", "sampleDir"),
        domain_effects=_DE_FRAGMENTOMICS,
    ),
    _in_process(
        "sample.methyl_extract",
        "methyl-extract",
        "sample.methyl_extract",
        "Extract BAM to per-chromosome HDF5 via native MethylExtractor (resolvedConfig.methyl_extract).",
        "sample_prep",
        _SAMPLE_MODULE,
        "MethylExtractTaskInput",
        _SAMPLE_MODULE,
        "MethylExtractTaskOutput",
        in_process_handler="_handle_methyl_extract",
        tool="MethylExtract",
        action_config_key="methyl_extract",
        context_vars=("sampleId", "sampleDir", "projectPath"),
        domain_effects=_DE_METHYL_EXTRACT,
    ),
    _in_process(
        "sample.extraction_qc",
        "methyl-extraction-qc",
        "sample.extraction_qc",
        "Evaluate MethylExtractor manifest guardrails and write extraction QC JSON.",
        "sample_prep",
        _SAMPLE_MODULE,
        "ExtractionQcTaskInput",
        _SAMPLE_MODULE,
        "ExtractionQcTaskOutput",
        in_process_handler="_handle_methyl_extraction_qc",
        tool="MethylExtractionQc",
        cli_tool="methyl-extraction-qc",
        action_config_key="extraction_qc",
        context_vars=("projectPath", "sampleId", "sampleDir"),
        domain_effects=_DE_EXTRACTION_QC,
    ),
    _in_process(
        "sample.archive_sample",
        "sample.archive-sample",
        "sample.archive_sample",
        "Archive sample bundle (FASTQs, QC JSON, HDF5) or QC-only reject record to durable storage.",
        "sample_prep",
        _SAMPLE_MODULE,
        "ArchiveSampleTaskInput",
        _SAMPLE_MODULE,
        "ArchiveSampleTaskOutput",
        in_process_handler="_handle_archive_sample",
        tool="SampleArchive",
        context_vars=(
            "sampleId",
            "sampleDir",
            "sampleDestination",
            "h5Destination",
            "projectPath",
            "mode",
            "rejectReason",
            "qcPath",
        ),
        domain_effects=_DE_ARCHIVE_SAMPLE,
    ),
    _in_process(
        "sample.delete_bam",
        "sample.delete-bam",
        "sample.delete_bam",
        "Delete BAM after methylation extraction to reclaim storage.",
        "sample_prep",
        _SAMPLE_MODULE,
        "DeleteBamTaskInput",
        _SAMPLE_MODULE,
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
        _SAMPLE_MODULE,
        "QcFailedTaskInput",
        _SAMPLE_MODULE,
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
        _VALIDATION_MODULE,
        "ValidationPlanTaskOutput",
        in_process_handler="_handle_validation_plan_iterations",
        action_config_key="validation",
        context_vars=("projectPath", "featureIterations", "qualityIterations"),
        domain_effects=_DE_PLAN_ITERATIONS,
    ),
    _in_process(
        "validation.stability",
        "validation.stability",
        "validation.stability",
        "Aggregate Monte Carlo DMP/gene stability and write production-ready panels.",
        "validation",
        _VALIDATION_MODULE,
        "StabilityTaskInput",
        _VALIDATION_MODULE,
        "ValidationStabilityOutput",
        in_process_handler="_handle_validation_stability",
        action_config_key="validation",
        context_vars=("projectPath", "monteCarloRunsRoot", "outputDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.biomarker_filter",
        "validation.biomarker-filter",
        "validation.biomarker_filter",
        "In-process disease CSV + PPI hub biomarker gene pool filter (MC stability).",
        "validation",
        _PIPELINE_MODULE,
        "BiomarkerFilterTaskInput",
        _PIPELINE_MODULE,
        "BiomarkerFilterTaskOutput",
        in_process_handler="_handle_validation_biomarker_filter",
        action_config_key="validation",
        context_vars=("projectPath", "runDir"),
    ),
    _in_process(
        "validation.prepare_freeze_project",
        "validation.prepare-freeze-project",
        "validation.prepare_freeze_project",
        "Write production/project.json with fixed_dmp_panel for granular freeze workflows.",
        "validation",
        _VALIDATION_MODULE,
        "PrepareFreezeTaskInput",
        _VALIDATION_MODULE,
        "ValidationPrepareFreezeOutput",
        in_process_handler="_handle_validation_prepare_freeze",
        action_config_key="validation",
        context_vars=("projectPath", "stableDmpCsv", "productionOutputDir"),
        domain_effects=_DE_PREPARE_FREEZE,
    ),
    _in_process(
        "validation.stability_freeze_readiness",
        "validation.stability-freeze-readiness",
        "validation.stability_freeze_readiness",
        "Audit stability, freeze, and progression artifacts before model training.",
        "validation",
        _VALIDATION_MODULE,
        "FreezeReadinessTaskInput",
        _VALIDATION_MODULE,
        "ValidationFreezeReadinessOutput",
        in_process_handler="_handle_validation_stability_freeze_readiness",
        action_config_key="validation",
        context_vars=("projectPath",),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.link_artifacts",
        "validation.link-artifacts",
        "validation.link_artifacts",
        "Symlink centroids/detections from a source MC run into a model-mc iteration dir.",
        "validation",
        _VALIDATION_MODULE,
        "LinkArtifactsTaskInput",
        _VALIDATION_MODULE,
        "ValidationLinkArtifactsOutput",
        in_process_handler="_handle_validation_link_artifacts",
        context_vars=("sourceRunDir", "targetRunDir", "runDir"),
        domain_effects=_DE_VALIDATION,
        internal=True,
    ),
    _in_process(
        "validation.model_bundle",
        "validation.model-bundle",
        "validation.model_bundle",
        "Build model feature bundle (tabular/generative) from frozen detections.",
        "validation",
        _VALIDATION_MODULE,
        "ModelBundleTaskInput",
        _VALIDATION_MODULE,
        "ValidationModelBundleOutput",
        in_process_handler="_handle_validation_model_bundle",
        context_vars=("projectPath", "bundleDir"),
        domain_effects=_DE_VALIDATION,
        internal=True,
    ),
    _in_process(
        "validation.model_train",
        "validation.model-train",
        "validation.model_train",
        "Train tabular or generative backend model for one MC model iteration.",
        "validation",
        _VALIDATION_MODULE,
        "ModelTrainTaskInput",
        _VALIDATION_MODULE,
        "ValidationModelTrainOutput",
        in_process_handler="_handle_validation_model_train",
        context_vars=("projectPath", "backend", "runDir", "bundleH5", "outputDir"),
        domain_effects=_DE_VALIDATION,
        internal=True,
    ),
    _in_process(
        "validation.model_predict",
        "validation.model-predict",
        "validation.model_predict",
        "Predict with tabular or generative backend for one MC model iteration.",
        "validation",
        _VALIDATION_MODULE,
        "ModelPredictTaskInput",
        _VALIDATION_MODULE,
        "ValidationModelPredictOutput",
        in_process_handler="_handle_validation_model_predict",
        context_vars=("projectPath", "backend", "runDir"),
        domain_effects=_DE_VALIDATION,
        internal=True,
    ),
    _in_process(
        "validation.select_best_model",
        "validation.select-best-model",
        "validation.select_best_model",
        "Rank model-mc backends and build final production model on all data.",
        "validation",
        _VALIDATION_MODULE,
        "SelectBestModelTaskInput",
        _VALIDATION_MODULE,
        "ValidationSelectBestModelOutput",
        in_process_handler="_handle_validation_select_best_model",
        action_config_key="validation",
        context_vars=("projectPath", "modelMcRoot", "backends", "selectionMetric", "selectionStat"),
        domain_effects=_DE_SELECT_BEST_MODEL,
    ),
    _in_process(
        "validation.model_mc",
        "validation.model-mc",
        "validation.model_mc",
        "Monte Carlo model training across backends (shared centroid/detector + per-backend model loops).",
        "validation",
        _VALIDATION_MODULE,
        "ModelMcTaskInput",
        _VALIDATION_MODULE,
        "ValidationModelMcOutput",
        in_process_handler="_handle_validation_model_mc",
        action_config_key="validation",
        context_vars=("projectPath", "monteCarloRunsRoot", "backends", "productionOutputDir"),
        domain_effects=_DE_VALIDATION,
    ),
    _in_process(
        "validation.post_model_validation",
        "validation.post-model-validation",
        "validation.post_model_validation",
        "Holdout evaluation with frozen production artifacts (predictor-only / frozen inference).",
        "validation",
        _VALIDATION_MODULE,
        "PostModelValidationTaskInput",
        _VALIDATION_MODULE,
        "ValidationPostModelValidationOutput",
        in_process_handler="_handle_validation_post_model_validation",
        action_config_key="validation",
        context_vars=("projectPath", "runDir", "productionOutputDir"),
        domain_effects=_DE_VALIDATION,
    ),
)


IDEMPOTENT_VALIDATION_ACTIONS: FrozenSet[str] = frozenset(
    {
        "validation.plan_iterations",
        "validation.stability",
        "validation.stability_freeze_readiness",
        "validation.prepare_freeze_project",
    }
)


def idempotency_enabled_for(entry: ActionCatalogEntry) -> bool:
    """Return True when signature-based skip/replay is active for this catalog entry."""
    if entry.idempotency_enabled:
        return True
    if entry.action_name in IDEMPOTENT_VALIDATION_ACTIONS:
        return True
    if entry.action_name.startswith("pipeline."):
        return True
    return False


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
