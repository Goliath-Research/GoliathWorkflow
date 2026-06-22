"""CLI argv builder for pipeline.gene_feature_select (methyl-gene-feature-select)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from methyl_gene_feature_select.core.runner import GENE_FEATURE_SELECTION_JSON, GENE_FEATURES_CLASSIFIER_CSV

from .base import CliAction, HandlerResult

GENE_FEATURE_SELECT_ARGV_MAP: Dict[str, str] = {
    "mapperDir": "--mapper-dir",
    "outputDir": "--output-dir",
    "maxFeatures": "--max-features",
    "targetBalancedAccuracy": "--target-ba",
}


class GeneFeatureSelectCliAction(CliAction):
    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        payload: Dict[str, Any] = dict(input_json)
        payload.pop("tool", None)
        payload.pop("project", None)
        payload.pop("projectPath", None)
        return super().build_argv(payload)

    def execute(self, input_json: Dict[str, Any]) -> HandlerResult:
        cmd = self.build_argv(input_json)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{cmd[0]} failed")

        output_dir = Path(str(input_json["outputDir"]))
        audit_path = output_dir / GENE_FEATURE_SELECTION_JSON
        out_csv = output_dir / GENE_FEATURES_CLASSIFIER_CSV
        payload: Dict[str, Any] = {
            "status": "ok",
            "tool": self.cli_tool,
            "stdout_tail": (proc.stdout or "")[-500:],
            "output_csv": str(out_csv) if out_csv.is_file() else None,
            "audit_path": str(audit_path) if audit_path.is_file() else None,
        }
        if audit_path.is_file():
            try:
                with open(audit_path, encoding="utf-8") as f:
                    audit = json.load(f)
                payload["n_features"] = audit.get("n_features")
            except Exception:
                pass
        if "skipping" in (proc.stdout or "").lower():
            payload["status"] = "skipped"
        return payload
