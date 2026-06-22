"""CLI argv builder for pipeline.gene_select (methyl-gene-select)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from methyl_gene_select.core.gene_featurecuts import (
    GENE_DMP_LOCI_CSV,
    GENE_FEATURECUTS_METRICS_JSON,
    GENES_CLASSIFIER_CSV,
    GENE_STABILITY_DIR,
)

from .base import CliAction, HandlerResult

GENE_SELECT_ARGV_MAP: Dict[str, str] = {
    "project": "--project",
    "projectPath": "--project",
    "runDir": "--run-dir",
    "maxGenes": "--max-genes",
    "maxDmps": "--max-dmps",
    "biomarkerFilter": "--biomarker-filter",
}


def default_run_dir_for_project(project: str) -> str:
    """
    Infer MC run directory from a project path without touching the filesystem.

    Project configs are files (e.g. ``.../configs/project.json``); iteration artifacts
    live alongside them in the parent directory or an explicit ``runDir``.
    """
    project_path = Path(str(project))
    if project_path.suffix:
        return str(project_path.parent)
    return str(project_path)


class GeneSelectCliAction(CliAction):
    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        payload: Dict[str, Any] = dict(input_json)
        biomarker = payload.pop("biomarkerFilter", None)
        project = payload.get("project") or payload.get("projectPath")
        if project and not payload.get("runDir"):
            payload["runDir"] = default_run_dir_for_project(str(project))
        cmd = super().build_argv(payload)
        if biomarker:
            cmd.append("--biomarker-filter")
        return cmd

    def execute(self, input_json: Dict[str, Any]) -> HandlerResult:
        cmd = self.build_argv(input_json)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{cmd[0]} failed")

        project = input_json.get("projectPath") or input_json.get("project")
        run_dir = input_json.get("runDir")
        if project and not run_dir:
            run_dir = default_run_dir_for_project(str(project))
        payload: Dict[str, Any] = {
            "status": "ok",
            "tool": self.cli_tool,
            "stdout_tail": (proc.stdout or "")[-500:],
            "run_dir": str(run_dir) if run_dir else None,
        }
        if run_dir:
            out_dir = Path(str(run_dir)) / GENE_STABILITY_DIR
            metrics_path = out_dir / GENE_FEATURECUTS_METRICS_JSON
            if metrics_path.is_file():
                try:
                    with open(metrics_path, encoding="utf-8") as f:
                        metrics = json.load(f)
                    payload["selected_k"] = metrics.get("selected_k")
                    payload["balanced_accuracy"] = metrics.get("balanced_accuracy")
                except Exception:
                    pass
            genes_csv = out_dir / GENES_CLASSIFIER_CSV
            loci_csv = out_dir / GENE_DMP_LOCI_CSV
            if genes_csv.is_file():
                payload["genes_classifier_csv"] = str(genes_csv)
            if loci_csv.is_file():
                payload["gene_dmp_loci_csv"] = str(loci_csv)
            if metrics_path.is_file():
                payload["metrics_json"] = str(metrics_path)
        return payload
