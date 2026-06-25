"""Strict task schema validation for split-detector workflow actions."""

from __future__ import annotations

import pytest

from methyl_worker.task_models.pipeline_models import (
    BiomarkerFilterSummary,
    BiomarkerFilterTaskOutput,
)
from methyl_worker.task_validation import (
    TaskValidationError,
    normalize_task_input,
    validate_task_input,
    validate_task_output,
)


def test_dmp_select_input_requires_chromosome_and_project() -> None:
    with pytest.raises(TaskValidationError):
        validate_task_input(
            "pipeline.dmp_select",
            "methyl-dmp-select",
            {"tool": "MethylDmpSelect", "projectPath": "/work/demo/project.json"},
        )

    validate_task_input(
        "pipeline.dmp_select",
        "methyl-dmp-select",
        {
            "tool": "MethylDmpSelect",
            "projectPath": "/work/demo/project.json",
            "chromosome": "1",
            "group": "PCa",
        },
    )


def test_dmp_select_input_strips_unknown_keys_before_validate() -> None:
    normalized = normalize_task_input(
        "pipeline.dmp_select",
        "methyl-dmp-select",
        {
            "tool": "MethylDmpSelect",
            "projectPath": "/work/demo/project.json",
            "chromosome": "1",
            "unexpected": True,
        },
    )
    assert "unexpected" not in normalized
    validate_task_input(
        "pipeline.dmp_select",
        "methyl-dmp-select",
        {
            "tool": "MethylDmpSelect",
            "projectPath": "/work/demo/project.json",
            "chromosome": "1",
            "unexpected": True,
        },
    )


def test_gene_select_input_requires_run_dir() -> None:
    with pytest.raises(TaskValidationError):
        validate_task_input(
            "pipeline.gene_select",
            "methyl-gene-select",
            {"tool": "MethylGeneSelect", "projectPath": "/work/demo/project.json"},
        )

    validate_task_input(
        "pipeline.gene_select",
        "methyl-gene-select",
        {
            "tool": "MethylGeneSelect",
            "projectPath": "/work/demo/project.json",
            "runDir": "/work/demo/monte_carlo_runs/run_0001",
            "biomarkerFilter": True,
        },
    )


def test_biomarker_filter_output_accepts_structured_payload() -> None:
    out = validate_task_output(
        "validation.biomarker_filter",
        "validation.biomarker-filter",
        BiomarkerFilterTaskOutput(
            status="ok",
            n_genes=42,
            outputCsv="/work/demo/gene_stability/biomarker_gene_pool.csv",
            biomarker_filter=BiomarkerFilterSummary(
                enabled=True,
                mode="ppi_only",
                biomarker_pool_size=42,
            ),
        ),
    )
    assert out.n_genes == 42


def test_gene_feature_select_input_strict() -> None:
    validate_task_input(
        "pipeline.gene_feature_select",
        "methyl-gene-feature-select",
        {
            "tool": "MethylGeneFeatureSelect",
            "mapperDir": "/work/demo/mapper/healthy/PCa",
            "outputDir": "/work/demo/gene_features",
            "maxFeatures": 500,
        },
    )
