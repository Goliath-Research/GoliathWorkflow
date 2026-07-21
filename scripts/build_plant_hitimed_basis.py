#!/usr/bin/env python3
"""Compose a plant HiTIMED hierarchy basis JSON (dev-time / operator offline).

Does NOT embed biology in the Python wheel. Operators supply leaf cell-type
markers (mesophyll / vasculature / …) and this script wraps them in a v2
hierarchy with ``analyte_trees.plant_tissue``. Point
``actionConfig.cell_deconvolution.hierarchy_basis_path`` at the output
(or register as cfg.reference_asset role ``hitimed_hierarchy_basis``).

Atlas JSON contract:

    {
      "citation": "...",
      "genome_build": "TAIR10",
      "root_name": "plant_root",
      "children": ["mesophyll", "vasculature"],
      "markers": [
        {"probe_id": "...", "chrom": "1", "pos": 123, "context": "CG",
         "betas": {"mesophyll": 0.9, "vasculature": 0.1}},
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def build_plant_hierarchy(atlas: Dict[str, Any]) -> Dict[str, Any]:
    markers = atlas.get("markers") or []
    if not markers:
        raise SystemExit("Atlas has no markers")
    children = [str(c) for c in (atlas.get("children") or atlas.get("cell_types") or [])]
    if len(children) < 2:
        raise SystemExit(
            "Atlas requires children or cell_types: [leaf_a, leaf_b, ...] "
            "(Houseman-style cell_types are accepted)."
        )
    root_name = str(atlas.get("root_name") or "plant_root")
    node_markers = []
    for m in markers:
        betas = m.get("betas") or {}
        missing = [c for c in children if c not in betas]
        if missing:
            raise SystemExit(f"Marker {m.get('probe_id')} missing betas for {missing}")
        node_markers.append(
            {
                "probe_id": m["probe_id"],
                "chrom": m["chrom"],
                "pos": m["pos"],
                "context": str(m.get("context") or "CG").upper(),
                "betas": {c: float(betas[c]) for c in children},
            }
        )
    return {
        "schema_version": 2,
        "basis_kind": "hierarchy",
        "source_package": "operator plant cell-type atlas",
        "citation": atlas.get("citation"),
        "genome_build": atlas.get("genome_build"),
        "coordinate_convention": atlas.get("coordinate_convention", "1-based"),
        "note": (
            "Plant HiTIMED tree for primary_analyte=plant_tissue. "
            "Not packaged in the methyldeconv wheel; provision under /work."
        ),
        "analyte_trees": {
            "plant_tissue": root_name,
            "default": root_name,
        },
        "nodes": {
            root_name: {
                "children": children,
                "markers": node_markers,
            }
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", type=Path, required=True, help="Operator plant atlas JSON")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("/work/cache/methyldeconv/plant_hitimed_hierarchy_v1.json"),
    )
    args = parser.parse_args(argv)
    if not args.atlas.is_file():
        raise SystemExit(f"Atlas not found: {args.atlas}")
    asset = build_plant_hierarchy(json.loads(args.atlas.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asset, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} (analyte_trees={list(asset['analyte_trees'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
