"""CLI argv builder for pipeline.gene_select (methyl-gene-select)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .base import CliAction

GENE_SELECT_ARGV_MAP: Dict[str, str] = {
    "project": "--project",
    "projectPath": "--project",
    "runDir": "--run-dir",
    "maxGenes": "--max-genes",
    "maxDmps": "--max-dmps",
    "biomarkerFilter": "--biomarker-filter",
}


class GeneSelectCliAction(CliAction):
    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        payload: Dict[str, Any] = dict(input_json)
        biomarker = payload.pop("biomarkerFilter", None)
        project = payload.get("project") or payload.get("projectPath")
        if project and not payload.get("runDir"):
            project_path = Path(str(project))
            payload["runDir"] = str(project_path.parent if project_path.is_file() else project_path)
        cmd = super().build_argv(payload)
        if biomarker:
            cmd.append("--biomarker-filter")
        return cmd
