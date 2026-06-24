"""Minimal valid golden I/O payloads per catalog action (source for JSON fixtures)."""

from __future__ import annotations

from typing import Any, Dict

_GUARD = {"overall_pass": True, "screening": {"disposition": "PASS"}}
_SCREEN = {"disposition": "PASS", "trim_front1": 0, "trim_tail1": 0, "trim_front2": 0, "trim_tail2": 0}

_FILE_FASTQ = {"type": "file", "basePath": "/data/fastq", "prefix": "S1/"}
_FILE_DEST = {"type": "file", "basePath": "/data/archive", "prefix": "studies/demo/S1/"}

GOLDEN_INPUTS: Dict[str, Dict[str, Any]] = {
    "pipeline.centroid": {"tool": "MethylCentroid", "projectPath": "/work/p/project.json"},
    "pipeline.detector": {"tool": "MethylDetector", "projectPath": "/work/p/project.json", "chromosome": "21"},
    "pipeline.dmp_select": {
        "tool": "MethylDmpSelect",
        "projectPath": "/work/p/project.json",
        "chromosome": "21",
    },
    "pipeline.mapper": {"tool": "MethylMapper", "projectPath": "/work/p/project.json", "chromosome": "21"},
    "pipeline.gene_select": {
        "tool": "MethylGeneSelect",
        "projectPath": "/work/p/project.json",
        "runDir": "/work/p/monte_carlo_runs/run_0001",
    },
    "pipeline.gene_feature_select": {
        "tool": "MethylGeneFeatureSelect",
        "mapperDir": "/work/p/mapper",
        "outputDir": "/work/p/gene_features",
    },
    "pipeline.enricher": {"tool": "MethylEnricher", "projectPath": "/work/p/project.json"},
    "pipeline.progression": {"tool": "MethylProgression", "projectPath": "/work/p/project.json"},
    "pipeline.classifier": {"tool": "MethylClassifier", "projectPath": "/work/p/project.json"},
    "pipeline.predictor": {"tool": "MethylPredictor", "projectPath": "/work/p/project.json"},
    "sample.download_fastq": {
        "tool": "SampleDownloadFastq",
        "sampleId": "S1",
        "sampleDir": "/work/samples/S1",
        "fastqSource": _FILE_FASTQ,
    },
    "sample.parabricks_fq2bam": {
        "tool": "ParabricksFq2Bam",
        "sampleId": "S1",
        "sampleDir": "/work/samples/S1",
        "referenceFasta": "/ref/genome.fa",
    },
    "sample.delete_fastqs": {"sampleId": "S1", "sampleDir": "/work/samples/S1"},
    "sample.trim_fastq": {"sampleId": "S1", "sampleDir": "/work/samples/S1"},
    "sample.methyl_qc": {"sampleId": "S1", "sampleDir": "/work/samples/S1", "projectPath": "/work/p/project.json"},
    "sample.fragmentomics": {"sampleId": "S1", "sampleDir": "/work/samples/S1", "projectPath": "/work/p/project.json"},
    "sample.methyl_extract": {
        "tool": "MethylExtract",
        "sampleId": "S1",
        "sampleDir": "/work/samples/S1",
        "projectPath": "/work/p/project.json",
    },
    "sample.extraction_qc": {"sampleId": "S1", "sampleDir": "/work/samples/S1"},
    "sample.archive_sample": {
        "tool": "SampleArchive",
        "sampleId": "S1",
        "sampleDir": "/work/samples/S1",
        "sampleDestination": _FILE_DEST,
    },
    "sample.upload_h5": {
        "tool": "SampleUploadH5",
        "sampleId": "S1",
        "sampleDir": "/work/samples/S1",
        "h5Destination": _FILE_DEST,
    },
    "sample.delete_bam": {"sampleId": "S1", "sampleDir": "/work/samples/S1"},
    "sample.qc_failed": {"sampleId": "S1", "sampleDir": "/work/samples/S1", "reason": "alignment_qc_failed"},
    "validation.plan_iterations": {"projectPath": "/work/p/project.json", "featureIterations": 2},
    "validation.stability": {"projectPath": "/work/p/project.json", "monteCarloRunsRoot": "/work/p/monte_carlo_runs"},
    "validation.biomarker_filter": {"projectPath": "/work/p/project.json", "runDir": "/work/p/monte_carlo_runs/run_0001"},
    "validation.prepare_freeze_project": {
        "projectPath": "/work/p/project.json",
        "monteCarloRunsRoot": "/work/p/monte_carlo_runs",
    },
    "validation.stability_freeze_readiness": {"projectPath": "/work/p/project.json"},
    "validation.link_artifacts": {
        "sourceRunDir": "/work/p/monte_carlo_runs/run_0001",
        "targetRunDir": "/work/p/monte_carlo_runs/model_mc/shared/run_0001",
    },
    "validation.model_bundle": {"projectPath": "/work/p/project.json"},
    "validation.model_train": {"projectPath": "/work/p/project.json", "backend": "tabular_sklearn"},
    "validation.model_predict": {"projectPath": "/work/p/project.json", "backend": "tabular_sklearn"},
    "validation.select_best_model": {"projectPath": "/work/p/project.json", "monteCarloRunsRoot": "/work/p/monte_carlo_runs"},
    "validation.model_mc": {"projectPath": "/work/p/project.json", "monteCarloRunsRoot": "/work/p/monte_carlo_runs"},
    "validation.post_model_validation": {
        "projectPath": "/work/p/project.json",
        "monteCarloRunsRoot": "/work/p/monte_carlo_runs",
    },
}

GOLDEN_OUTPUTS: Dict[str, Dict[str, Any]] = {
    "pipeline.centroid": {
        "status": "ok",
        "chromosome": "21",
        "context": "CG",
        "output_dir": "/work/p/centroids",
        "centroid_h5_path": "/work/p/centroids/21-CG.h5",
        "n_samples": 10,
    },
    "pipeline.detector": {
        "status": "ok",
        "chromosome": "21",
        "context": "CG",
        "n_statistical_dmps": 1000,
        "n_biological_dmps": 200,
    },
    "pipeline.dmp_select": {"status": "ok", "chromosome": "21", "n_dmps_classifier": 50},
    "pipeline.mapper": {"status": "ok", "chromosome": "21", "n_output_genes": 120},
    "pipeline.gene_select": {"status": "ok", "run_dir": "/work/p/mc/run_0001", "selected_k": 25},
    "pipeline.gene_feature_select": {"status": "ok", "n_features": 32, "output_csv": "/work/p/out.csv"},
    "pipeline.enricher": {"status": "ok", "all_complete": True, "n_comparisons": 1},
    "pipeline.progression": {"status": "ok", "n_comparisons": 3},
    "pipeline.classifier": {"status": "ok", "model_path": "/work/p/models/model.pkl"},
    "pipeline.predictor": {"status": "ok", "balanced_accuracy": 0.85},
    "sample.download_fastq": {"status": "ok", "sampleId": "S1", "fastqFiles": ["S1_1.fastq.gz"], "n_files": 1},
    "sample.parabricks_fq2bam": {
        "status": "ok",
        "sampleId": "S1",
        "bamPath": "/work/samples/S1/S1.bam",
    },
    "sample.delete_fastqs": {"status": "ok", "sampleId": "S1", "deleted": True, "n_files_removed": 2},
    "sample.trim_fastq": {
        "status": "ok",
        "sampleId": "S1",
        "trimmedR1": "/work/samples/S1/S1_1.trimmed.fastq.gz",
        "trimmedR2": "/work/samples/S1/S1_2.trimmed.fastq.gz",
    },
    "sample.methyl_qc": {
        "status": "ok",
        "sampleId": "S1",
        "qcPath": "/work/qc/S1.json",
        "guardrails": _GUARD,
        "screening": _SCREEN,
    },
    "sample.fragmentomics": {"status": "ok", "sampleId": "S1", "outputDir": "/work/frag/S1"},
    "sample.methyl_extract": {"status": "ok", "sampleId": "S1", "h5Files": ["21-CG.h5"], "n_h5_files": 1},
    "sample.extraction_qc": {
        "status": "ok",
        "sampleId": "S1",
        "qcPath": "/work/samples/S1/S1.extraction_qc.json",
        "guardrails": _GUARD,
        "extraction_pass": True,
    },
    "sample.archive_sample": {
        "status": "ok",
        "sampleId": "S1",
        "archiveMode": "full",
        "remotePrefix": "studies/demo/S1/",
        "sampleArchived": True,
    },
    "sample.upload_h5": {
        "status": "ok",
        "sampleId": "S1",
        "archiveMode": "full",
        "remotePrefix": "studies/demo/S1/",
        "sampleArchived": True,
    },
    "sample.delete_bam": {"status": "ok", "sampleId": "S1", "deleted": True, "n_files_removed": 1},
    "sample.qc_failed": {"sampleId": "S1", "status": "QC_FAILED", "reason": "alignment_qc_failed"},
    "validation.plan_iterations": {
        "status": "ok",
        "projectPath": "/work/p/project.json",
        "n_iterations": 2,
        "iterations": [{"run_id": "run_0001", "iteration": 1}],
    },
    "validation.stability": {
        "status": "ok",
        "outputDir": "/work/p/monte_carlo_runs/stability",
        "summary": {"n_iterations": 5, "n_stable_dmps": 100},
    },
    "validation.biomarker_filter": {
        "status": "ok",
        "n_genes": 50,
        "outputCsv": "/work/p/gene_stability/biomarker_gene_pool.csv",
        "biomarker_filter": {"enabled": True, "mode": "ppi"},
    },
    "validation.prepare_freeze_project": {
        "status": "ok",
        "productionOutputDir": "/work/p/monte_carlo_runs/production",
        "projectPath": "/work/p/project.json",
    },
    "validation.stability_freeze_readiness": {"status": "ok", "ready": True, "outputDir": "/work/p"},
    "validation.link_artifacts": {"status": "ok", "linked_files": ["centroids", "detections"]},
    "validation.model_bundle": {
        "status": "ok",
        "bundleDir": "/work/p/model_bundle",
        "bundleH5": "/work/p/model_bundle/model_feature_bundle.h5",
    },
    "validation.model_train": {
        "status": "ok",
        "model_path": "/work/p/models/tabular-model.joblib",
        "backend": "tabular_sklearn",
    },
    "validation.model_predict": {
        "status": "ok",
        "predictions_path": "/work/p/predictions.csv",
        "n_samples": 20,
    },
    "validation.select_best_model": {
        "status": "ok",
        "selectedBackend": "tabular_sklearn",
        "selectionMetric": "balanced_accuracy",
    },
    "validation.model_mc": {"status": "ok", "modelMcRoot": "/work/p/monte_carlo_runs/model_mc", "n_iterations": 3},
    "validation.post_model_validation": {
        "status": "ok",
        "outputDir": "/work/p/post_model_validation/run_0001",
        "passed": True,
    },
}
