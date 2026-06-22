"""
Migrate legacy step_config.detection selection keys into dmp_selection / gene_selection / classifier.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

DMP_SELECTION_KEYS = {
    "classifier_dmp_selection",
    "target_balanced_accuracy",
    "featurecuts_max_k_cap",
    "featurecuts_exhaustive_search",
    "featurecuts_max_candidates",
    "min_core_dmps",
    "min_selected_dmps",
    "classifier_export_margin_pct",
    "classifier_export_margin_abs",
    "classifier_export_max_dmps",
    "dynamic_dmp_cutoff_enabled",
    "dynamic_dmp_cutoff_relaxation",
}

CLASSIFIER_KEYS = {
    "temperature",
    "enable_platt_calibration",
    "export_classifier",
}

GENE_SELECTION_MC_KEYS = {
    "stability_gene_biomarker_filter_enabled",
    "stability_gene_biomarker_mode",
    "stability_gene_biomarker_top_genes",
    "stability_gene_biomarker_ppi_top_hubs",
    "stability_gene_biomarker_min_degree",
    "stability_gene_region_hits",
    "stability_gene_featurecuts_max_genes",
    "stability_gene_featurecuts_max_dmps",
}


def migrate_step_config(step_config: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    """Split legacy detection keys into focused step_config sections."""
    warnings: list[str] = []
    out = dict(step_config)
    detection = dict(out.get("detection") or {})
    if not detection:
        return out, warnings

    dmp = dict(out.get("dmp_selection") or {})
    classifier = dict(out.get("classifier") or {})
    gene_sel = dict(out.get("gene_selection") or {})
    validation = dict(out.get("validation") or {})

    moved_dmp = {k: detection.pop(k) for k in list(detection.keys()) if k in DMP_SELECTION_KEYS}
    moved_clf = {k: detection.pop(k) for k in list(detection.keys()) if k in CLASSIFIER_KEYS}
    moved_gene = {k: validation.pop(k) for k in list(validation.keys()) if k in GENE_SELECTION_MC_KEYS}

    if moved_dmp:
        dmp.update(moved_dmp)
        out["dmp_selection"] = dmp
        warnings.append(f"Migrated {len(moved_dmp)} key(s) from detection → dmp_selection")
    if moved_clf:
        classifier.update(moved_clf)
        out["classifier"] = classifier
        warnings.append(f"Migrated {len(moved_clf)} key(s) from detection → classifier")
    if moved_gene:
        gene_sel.update(moved_gene)
        out["gene_selection"] = gene_sel
        warnings.append(f"Migrated {len(moved_gene)} key(s) from validation → gene_selection")

    if detection != out.get("detection"):
        out["detection"] = detection
    if validation != out.get("validation"):
        out["validation"] = validation

    return out, warnings


def migrate_project_json(path: Path, *, write: bool = False) -> Tuple[Dict[str, Any], list[str]]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    step_config = payload.get("step_config") or {}
    migrated, warnings = migrate_step_config(step_config)
    payload["step_config"] = migrated
    if write:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
    return payload, warnings


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Migrate detection config to split step_config sections")
    parser.add_argument("project_json", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    _payload, warnings = migrate_project_json(args.project_json, write=args.write)
    for w in warnings:
        print(w)
    if not warnings:
        print("No migration changes needed.")


if __name__ == "__main__":
    main()
