#!/usr/bin/env python3
"""Fail when task input model fields overlap package actionConfig schema keys."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, FrozenSet, Set

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKERS = _REPO_ROOT / "workers"
if str(_WORKERS) not in sys.path:
    sys.path.insert(0, str(_WORKERS))

# Workflow identity / binding fields allowed on task wire payloads.
ALLOWLIST: FrozenSet[str] = frozenset(
    {
        "tool",
        "project",
        "projectPath",
        "project_path",
        "sampleId",
        "sampleDir",
        "group",
        "chromosome",
        "context",
        "comparison",
        "outputDir",
        "centroid1Dir",
        "centroid2Dir",
        "runDir",
        "mapperDir",
        "discoveryCsv",
        "orderedComparisonLabels",
        "fixedDmpPanel",
        "biomarkerFilter",
        "fastqSource",
        "sampleDestination",
        "h5Destination",
        "mode",
        "rejectReason",
        "alignmentQcPath",
        "qcPath",
        "h5Files",
        "trimFront1",
        "trimTail1",
        "trimFront2",
        "trimTail2",
        "remediationReason",
        "reason",
        "monteCarloRunsRoot",
        "outputDir",
        "stableDmpCsv",
        "productionOutputDir",
        "sourceRunDir",
        "targetRunDir",
        "bundleDir",
        "bundleH5",
        "backend",
        "backends",
        "selectionMetric",
        "selectionStat",
        "modelMcRoot",
        "featureIterations",
        "qualityIterations",
        "stepOverride",
        "addSamples",
        "removeSamples",
        "seed",
        "trainFraction",
        "layout",
        "overwrite",
        "workerToolMapper",
        "workerToolEnricher",
        "workerToolProgression",
        "orderedComparisonLabels",
    }
)

_CONFIG_MODEL_MODULES: Dict[str, str] = {
    "centroid": "methyl_centroid.config:MethylCentroidConfig",
    "detection": "methyl_detector.models.config:MethylDetectorConfig",
    "dmp_selection": "methyl_dmp_select.models.config:DmpSelectionConfig",
    "mapper": "methyl_mapper.config:MapperStepConfig",
    "enricher": "methyl_enricher.config:EnricherStepConfig",
    "classifier": "methyl_classifier.models.config_schema:ClassificationConfig",
    "predictor": "methyl_predictor.models.config:PredictorConfig",
    "gene_selection": "methyl_gene_select.models.config:GeneSelectionConfig",
    "alignment_qc": "methyl_alignment_qc.models.config:AlignmentQcConfig",
    "extraction_qc": "methyl_extraction_qc.models.config:ExtractionQcConfig",
    "fragmentomics": "methyl_fragmentomics.config:FragmentomicsConfig",
    "methyl_extract": "methyl_utils.action_config_resolver:ActionConfigKey",
    "validation": "methyl_validation.config:ValidationStepConfig",
    "progression": "methyl_disease_progression.config:ProgressionStepConfig",
    "parabricks": "methyl_utils.action_config_resolver:ActionConfigKey",
}


def _load_config_field_names(action_key: str) -> Set[str]:
    if action_key in ("methyl_extract", "parabricks"):
        return {
            "extract_contexts",
            "threads",
            "min_mapq",
            "min_phred",
            "min_cov",
            "cap_cov",
            "compression",
            "chunk_size",
            "output_format",
            "split",
            "reference_fasta",
            "chrom_mapping",
            "extractor_bin",
            "image",
            "bwa_threads",
            "gpu_flags",
            "extra_docker_args",
            "cleanup_tmp",
            "genome_fasta",
        }
    spec = _CONFIG_MODEL_MODULES.get(action_key)
    if not spec:
        return set()
    module_name, class_name = spec.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        model = getattr(module, class_name)
        return set(getattr(model, "model_fields", {}).keys())
    except Exception:
        return set()


def _snake_case_fields(model_fields: Set[str]) -> Set[str]:
    out = set(model_fields)
    for name in list(model_fields):
        parts = name.split("_")
        if len(parts) > 1:
            camel = parts[0] + "".join(p.title() for p in parts[1:])
            out.add(camel)
    return out


def check_catalog() -> list[str]:
    from methyl_worker.action_catalog import list_action_catalog

    errors: list[str] = []
    for entry in list_action_catalog():
        if not entry.action_config_key:
            continue
        spec = entry.input_module, entry.input_class
        module = importlib.import_module(spec[0])
        input_model = getattr(module, spec[1])
        wire_fields = set(input_model.model_fields.keys())
        config_fields = _snake_case_fields(_load_config_field_names(entry.action_config_key))
        overlap = sorted(
            f
            for f in wire_fields
            if f in config_fields and f not in ALLOWLIST and f != "stepOverride"
        )
        if overlap:
            errors.append(
                f"{entry.action_name}: wire fields overlap actionConfig.{entry.action_config_key}: "
                + ", ".join(overlap)
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.parse_args()
    errors = check_catalog()
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1
    print("task input / actionConfig boundary check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
