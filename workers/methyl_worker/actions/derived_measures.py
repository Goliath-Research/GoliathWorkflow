"""CLI argv builder for pipeline.derived_measures."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import CliAction


DERIVED_MEASURES_ARGV_MAP: Dict[str, str] = {
    "project": "--project",
    "projectPath": "--project",
    "outputDir": "--output-dir",
    "stepOverride": "--step-override",
    "resolvedConfigPath": "--resolved-config",
}


class DerivedMeasuresCliAction(CliAction):
    """Build methyl-derived-measures argv."""

    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        payload: Dict[str, Any] = dict(input_json)
        for drop_key in ("chromosome", "context", "comparison", "group"):
            payload.pop(drop_key, None)
        return super().build_argv(payload)
