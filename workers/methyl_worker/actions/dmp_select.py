"""CLI argv builder for pipeline.dmp_select (methyl-dmp-select)."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import CliAction
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
