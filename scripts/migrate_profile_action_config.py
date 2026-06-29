#!/usr/bin/env python3
"""Collapse duplicate actionConfig keys in pipeline profile JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROFILE_DIR = _REPO_ROOT / "workflow_engine" / "domain" / "profiles"

_DMP_MIRROR_KEYS = {
    "stability_target_balanced_accuracy": "target_balanced_accuracy",
    "stability_min_core_dmps": "min_core_dmps",
    "stability_classifier_export_margin_pct": "classifier_export_margin_pct",
    "stability_classifier_export_margin_abs": "classifier_export_margin_abs",
    "stability_classifier_export_max_dmps": "classifier_export_max_dmps",
}

_GENE_CAP_KEYS = {
    "stability_gene_featurecuts_max_genes": "max_genes",
    "stability_gene_featurecuts_max_dmps": "max_dmps",
}


def _migrate_profile(data: Dict[str, Any]) -> bool:
    changed = False
    ac = data.get("actionConfig")
    if not isinstance(ac, dict):
        return False

    validation = ac.get("validation")
    if isinstance(validation, dict):
        dmp_sel = ac.setdefault("dmp_selection", {})
        if not isinstance(dmp_sel, dict):
            dmp_sel = {}
            ac["dmp_selection"] = dmp_sel
        for val_key, dmp_key in _DMP_MIRROR_KEYS.items():
            if val_key not in validation:
                continue
            if dmp_key in dmp_sel:
                validation.pop(val_key)
                changed = True
            else:
                dmp_sel[dmp_key] = validation.pop(val_key)
                changed = True

        gene_sel = ac.setdefault("gene_selection", {})
        if not isinstance(gene_sel, dict):
            gene_sel = {}
            ac["gene_selection"] = gene_sel
        for val_key, gene_key in _GENE_CAP_KEYS.items():
            if val_key not in validation:
                continue
            if gene_key in gene_sel:
                validation.pop(val_key)
                changed = True
            else:
                gene_sel[gene_key] = validation.pop(val_key)
                changed = True

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Apply changes to profile files")
    args = parser.parse_args()

    any_changed = False
    for path in sorted(_PROFILE_DIR.glob("*.profile.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if _migrate_profile(data):
            any_changed = True
            print(f"would update: {path.name}")
            if args.write:
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                print(f"  wrote {path.name}")

    if not any_changed:
        print("no profile changes needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
