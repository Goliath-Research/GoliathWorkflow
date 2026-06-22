"""CLI argv builder for pipeline.dmp_select (methyl-dmp-select)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import CliAction, HandlerResult
from .detector import merge_detector_step_override, resolve_detector_group

DMP_SELECT_ARGV_MAP: Dict[str, str] = {
    "project": "--project",
    "projectPath": "--project",
    "group": "--group",
    "chromosome": "--chromosome",
    "discoveryCsv": "--discovery-csv",
    "outputDir": "--output-dir",
    "stepOverride": "--step-override",
}


class DmpSelectCliAction(CliAction):
    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        payload: Dict[str, Any] = dict(input_json)
        override = merge_detector_step_override(payload)
        if override is not None:
            payload["stepOverride"] = override
        group = resolve_detector_group(payload)
        if group is not None:
            payload["group"] = group
        for drop_key in (
            "context",
            "comparison",
            "fixedDmpPanel",
            "addSamples",
            "removeSamples",
        ):
            payload.pop(drop_key, None)
        return super().build_argv(payload)

    def execute(self, input_json: Dict[str, Any]) -> HandlerResult:
        cmd = self.build_argv(input_json)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{cmd[0]} failed")

        chrom = str(input_json.get("chromosome") or "")
        payload: Dict[str, Any] = {
            "status": "ok",
            "tool": self.cli_tool,
            "stdout_tail": (proc.stdout or "")[-500:],
            "chromosome": chrom or None,
        }
        audit = _load_dmp_selection_audit(input_json, chrom)
        if audit:
            payload.update(audit)
        return payload


def _step_override_path(step_override: Any) -> Optional[Path]:
    if step_override is None or step_override == "":
        return None
    if isinstance(step_override, (str, Path)):
        return Path(step_override)
    if isinstance(step_override, dict):
        fd, path = tempfile.mkstemp(suffix=".json", prefix="dmp-select-step-")
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(step_override, f)
        return Path(path)
    return None


def _load_dmp_selection_audit(input_json: Dict[str, Any], chrom: str) -> Dict[str, Any]:
    if not chrom:
        return {}
    project = input_json.get("projectPath") or input_json.get("project")
    output_dir = input_json.get("outputDir")
    if not output_dir and project:
        try:
            from methyl_dmp_select.utils.project_resolver import resolve_dmp_selection_config

            cfg = resolve_dmp_selection_config(
                str(project),
                comparison=resolve_detector_group(input_json),
                chromosome=chrom,
                step_override_path=_step_override_path(input_json.get("stepOverride")),
            )
            output_dir = cfg.output_dir
        except Exception:
            return {}
    if not output_dir:
        return {}

    out = Path(str(output_dir))
    audit_path = out / f"dmp_selection-{chrom}.json"
    if not audit_path.is_file():
        return {}

    try:
        with open(audit_path, encoding="utf-8") as f:
            audit = json.load(f)
    except Exception:
        return {}

    status = "skipped" if not (out / f"dmps-{chrom}-classifier.csv").is_file() else "ok"
    return {
        "status": status,
        "n_dmps_discovery": audit.get("n_dmps_discovery"),
        "n_dmps_classifier": audit.get("n_dmps_classifier"),
        "n_dmps_extended": audit.get("n_dmps_extended"),
        "discovery_csv": audit.get("discovery_csv"),
        "classifier_csv": str(out / f"dmps-{chrom}-classifier.csv"),
        "extended_csv": str(out / f"dmps-{chrom}-classifier-extended.csv"),
        "audit_path": str(audit_path),
    }
