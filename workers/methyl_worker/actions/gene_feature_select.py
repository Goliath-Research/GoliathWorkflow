"""CLI argv builder for pipeline.gene_feature_select (methyl-gene-feature-select)."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import CliAction

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
