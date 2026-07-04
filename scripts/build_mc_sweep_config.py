#!/usr/bin/env python3
"""
Build a MonteCarloConfig JSON for analyte MC sweeps on shared /work storage.

Merges profile validation (METHYL_PROFILE) with an optional sweep overlay, writes
mc_config.json under the sweep analyte directory, and prints the resolved project
output root (output_base / project_name).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ensure repo packages import when run outside an installed wheel layout.
for rel in (
    "packages/methylutils",
    "packages/methylvalidation",
    "packages/methylgeneselect",
):
    pkg_root = REPO_ROOT / rel
    if pkg_root.is_dir() and str(pkg_root) not in sys.path:
        sys.path.insert(0, str(pkg_root))

from methyl_utils import load_project  # noqa: E402
from methyl_utils.action_config_resolver import resolve_for_project  # noqa: E402
from methyl_validation.cohort_inference import infer_monte_carlo_cohorts_from_project  # noqa: E402
from methyl_validation.config import MonteCarloConfig  # noqa: E402
from methyl_validation.mc_config_load import (  # noqa: E402
    apply_project_regulatory_to_mc_dict,
    write_mc_config_snapshot,
)
from methyl_validation.modeling_modes import apply_modeling_modes_to_validation_dict  # noqa: E402

_GENE_SELECTION_TO_VALIDATION = {
    "min_selected_genes": "stability_min_selected_genes",
    "target_balanced_accuracy": "stability_target_balanced_accuracy",
    "max_genes": "stability_gene_featurecuts_max_genes",
    "max_dmps": "stability_gene_featurecuts_max_dmps",
    "dmp_source": "stability_gene_featurecuts_dmp_source",
}


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_gene_selection_into_validation(validation: Dict[str, Any], overlay: Dict[str, Any]) -> None:
    gene_sel = overlay.pop("gene_selection", None)
    if not isinstance(gene_sel, dict):
        return
    for src, dst in _GENE_SELECTION_TO_VALIDATION.items():
        if src in gene_sel and gene_sel[src] is not None:
            validation[dst] = gene_sel[src]
    # Aliases used by modeling_modes
    if gene_sel.get("min_selected_genes") is not None:
        validation.setdefault("gene_featurecuts_min_genes", gene_sel["min_selected_genes"])
    if gene_sel.get("target_balanced_accuracy") is not None:
        validation.setdefault("gene_featurecuts_target_ba", gene_sel["target_balanced_accuracy"])
    if gene_sel.get("max_genes") is not None:
        validation.setdefault("gene_featurecuts_max_genes", gene_sel["max_genes"])


def build_mc_config_dict(
    project_path: Path,
    *,
    output_base: Path,
    overlay: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    project_data = _load_json(project_path)
    if "step_config" in project_data:
        raise SystemExit(
            f"{project_path} still contains step_config; migrate and set METHYL_PROFILE."
        )

    project = load_project(str(project_path))
    validation = dict(resolve_for_project("validation", project))
    if not validation:
        raise SystemExit(
            f"No validation actionConfig resolved for {project_path}. Set METHYL_PROFILE."
        )

    overlay = dict(overlay or {})
    _merge_gene_selection_into_validation(validation, overlay)
    validation.update({k: v for k, v in overlay.items() if k != "gene_selection"})
    validation = apply_modeling_modes_to_validation_dict(validation)
    for scope_flag in (
        "runDmpSelection",
        "runGeneFeaturecuts",
        "runBiomarkerFilter",
        "runGeneFeatureSelect",
    ):
        validation.pop(scope_flag, None)

    cohorts = infer_monte_carlo_cohorts_from_project(project_data, str(project_path))
    if len(cohorts) < 2:
        raise SystemExit(f"Could not infer >=2 MC cohorts from {project_path}")

    mc_dict = apply_project_regulatory_to_mc_dict(
        {
            "samples_base_path": project_data.get("samples_base_path", "/work/samples"),
            "base_project": str(project_path.resolve()),
            "output_base": str(output_base.resolve()),
            "path_remap": project_data.get("path_remap"),
            "cohorts": cohorts,
            "run_stability": True,
            **validation,
        },
        project,
    )
    return mc_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MonteCarloConfig for analyte MC sweeps.")
    parser.add_argument("--project", "-p", type=Path, required=True, help="Study manifest JSON.")
    parser.add_argument(
        "--output-base",
        type=Path,
        required=True,
        help="Sweep output base (e.g. /work/projects/prostate-cancer/sweeps/run001).",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        default=None,
        help="JSON overlay merged into validation (see scripts/config/analyte_sweep.example.json).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Write mc_config.json here.",
    )
    parser.add_argument(
        "--print-project-root",
        action="store_true",
        help="Print output_base/project_name on stdout (for shell scripts).",
    )
    args = parser.parse_args()

    overlay: Dict[str, Any] = {}
    if args.overlay is not None:
        overlay = _load_json(args.overlay)

    mc_dict = build_mc_config_dict(
        args.project,
        output_base=args.output_base,
        overlay=overlay,
    )
    config = MonteCarloConfig.model_validate(mc_dict)
    write_mc_config_snapshot(config, args.out)

    if args.print_project_root:
        project = load_project(str(args.project))
        print((args.output_base / project.project_name).resolve())


if __name__ == "__main__":
    main()
