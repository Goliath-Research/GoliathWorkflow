"""Build gene-select runtime config from pipeline project JSON."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Union

from methyl_utils import load_project
from methyl_utils.action_config_resolver import resolve_for_project

_GENE_SELECTION_ALIASES: Dict[str, str] = {
    "target_balanced_accuracy": "stability_target_balanced_accuracy",
    "min_selected_genes": "stability_min_selected_genes",
    "max_genes": "stability_gene_featurecuts_max_genes",
    "max_dmps": "stability_gene_featurecuts_max_dmps",
    "biomarker_filter_enabled": "stability_gene_biomarker_filter_enabled",
    "biomarker_mode": "stability_gene_biomarker_mode",
    "biomarker_region_hits": "stability_gene_region_hits",
    "biomarker_top_genes": "stability_gene_biomarker_top_genes",
    "biomarker_ppi_top_hubs": "stability_gene_biomarker_ppi_top_hubs",
    "biomarker_min_degree": "stability_gene_biomarker_min_degree",
}

_VALIDATION_GENE_KEYS = (
    "stability_gene_featurecuts_enabled",
    "stability_gene_featurecuts_max_genes",
    "stability_gene_featurecuts_max_dmps",
    "stability_gene_biomarker_filter_enabled",
    "stability_gene_biomarker_mode",
    "stability_gene_region_hits",
    "stability_gene_biomarker_top_genes",
    "stability_gene_biomarker_ppi_top_hubs",
    "stability_gene_biomarker_min_degree",
    "stability_gene_biomarker_ppi_cache_path",
    "stability_target_balanced_accuracy",
    "stability_min_selected_genes",
)


def build_gene_select_config(
    project_path: Union[str, Path],
    **overrides: Any,
) -> SimpleNamespace:
    """
    Merge profile ``actionConfig.gene_selection`` and validation MC keys into a config object
    suitable for ``run_gene_featurecuts_for_iteration``.
    """
    project = load_project(project_path)
    payload: Dict[str, Any] = {"stability_gene_featurecuts_enabled": True}

    gene_sel = dict(resolve_for_project("gene_selection", project))
    for src, dst in _GENE_SELECTION_ALIASES.items():
        if src in gene_sel and gene_sel[src] is not None:
            payload[dst] = gene_sel[src]

    validation = dict(resolve_for_project("validation", project))
    for key in _VALIDATION_GENE_KEYS:
        if key in validation and validation[key] is not None:
            payload[key] = validation[key]

    payload.update({k: v for k, v in overrides.items() if v is not None})
    return SimpleNamespace(**payload)
