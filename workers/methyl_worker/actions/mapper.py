"""CLI argv builder for pipeline.mapper (methyl-mapper contract)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..task_models.step_override_models import MapperStepOverride
from .base import CliAction
from .detector import resolve_detector_group

# methyl-mapper accepts --project, --group, and --step-override only (no --comparison / --chromosome).
MAPPER_ARGV_MAP: Dict[str, str] = {
    "project": "--project",
    "projectPath": "--project",
    "project_path": "--project",
    "group": "--group",
    "stepOverride": "--step-override",
}


def merge_mapper_step_override(input_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fold workflow scope fields into a methyl-mapper --step-override JSON file."""
    raw = input_json.get("stepOverride")
    if isinstance(raw, MapperStepOverride):
        data = raw.model_dump(exclude_none=True, exclude_unset=True)
    elif isinstance(raw, dict):
        data = {k: v for k, v in raw.items() if v is not None}
    else:
        data = {}

    resolved = input_json.get("resolvedConfig")
    if isinstance(resolved, dict):
        mapper_cfg = resolved.get("mapper")
        if isinstance(mapper_cfg, dict):
            for key in ("csv_pattern", "csv_filename_pattern", "output_dir", "enrich_disease"):
                if mapper_cfg.get(key) is not None and key not in data:
                    data[key] = mapper_cfg[key]

    project = (
        input_json.get("projectPath")
        or input_json.get("project")
        or input_json.get("project_path")
    )
    if project:
        override_path = Path(str(project)).expanduser().resolve().parent / "mapper_step_override.json"
        if override_path.is_file():
            try:
                file_data = json.loads(override_path.read_text(encoding="utf-8"))
                if isinstance(file_data, dict):
                    merged = {k: v for k, v in file_data.items() if v is not None}
                    merged.update(data)
                    data = merged
            except (OSError, json.JSONDecodeError):
                pass

    output_dir = input_json.get("outputDir")
    if output_dir not in (None, ""):
        data["output_dir"] = str(output_dir)

    if not data:
        return None

    override = MapperStepOverride.model_validate(data)
    payload = override.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    return payload or None


class MapperCliAction(CliAction):
    """Build methyl-mapper argv without unsupported workflow-only flags."""

    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        payload: Dict[str, Any] = dict(input_json)
        override = merge_mapper_step_override(payload)
        if override is not None:
            payload["stepOverride"] = override
        group = resolve_detector_group(payload)
        if group is not None:
            payload["group"] = group
        for drop_key in (
            "chromosome",
            "context",
            "comparison",
            "outputDir",
            "fixedDmpPanel",
            "addSamples",
            "removeSamples",
        ):
            payload.pop(drop_key, None)
        return super().build_argv(payload)
