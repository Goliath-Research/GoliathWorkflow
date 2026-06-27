#!/usr/bin/env python3
"""One-way migration: legacy project.json (with step_config) → slim manifest + profile + site."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

SITE_KEYS = {
    "alignment_qc": ["genome_fasta"],
    "methyl_extract": ["reference_fasta", "threads", "extract_contexts", "min_mapq", "min_phred", "split", "output_format"],
    "mapper": ["gtf", "methyl_mapper_home", "cache_ttl_days", "grok_cache_ttl_days"],
    "enricher": ["network_refinement"],
    "parabricks": [],
}

INFRA_MAPPER = {
    "genome_fasta": ("reference_genome", "fasta"),
    "reference_fasta": ("reference_genome", "fasta"),
    "gtf": ("annotation", "gtf"),
    "methyl_mapper_home": ("methyl_mapper_home", None),
}


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(dict(out[k]), v)
        else:
            out[k] = deepcopy(v)
    return out


def extract_site_and_profile(step_config: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    site: Dict[str, Any] = {"actionConfig": {}}
    profile_action: Dict[str, Any] = deepcopy(step_config)

    for section, keys in SITE_KEYS.items():
        block = profile_action.get(section)
        if not isinstance(block, dict):
            continue
        site_block: Dict[str, Any] = {}
        for key in list(block.keys()):
            if key in INFRA_MAPPER or key in ("genome_fasta", "gtf", "methyl_mapper_home", "reference_fasta"):
                val = block.pop(key)
                if key in INFRA_MAPPER:
                    top, sub = INFRA_MAPPER[key]
                    if sub:
                        site.setdefault(top, {})[sub] = val
                    else:
                        site[top] = val
                else:
                    site_block[key] = val
        if site_block:
            site["actionConfig"][section] = site_block

    nr = step_config.get("enricher", {}).get("network_refinement") if isinstance(step_config.get("enricher"), dict) else None
    if isinstance(nr, dict) and nr.get("cache_path"):
        site.setdefault("caches", {})["string_edges"] = nr["cache_path"]

    return site, profile_action


def slim_manifest(data: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(data)
    sc = out.pop("step_config", {}) or {}
    val = sc.get("validation") if isinstance(sc.get("validation"), dict) else {}
    if out.get("regulatory") is None and isinstance(val.get("regulatory"), dict):
        out["regulatory"] = val["regulatory"]
    if out.get("validation_partitions") is None and isinstance(val.get("validation_partitions"), dict):
        out["validation_partitions"] = val["validation_partitions"]
    if out.get("progression_order") is None:
        prog = sc.get("progression") if isinstance(sc.get("progression"), dict) else {}
        if prog.get("ordered_comparison_labels"):
            out["progression_order"] = "explicit"
            out["progression_labels"] = prog["ordered_comparison_labels"]
        elif _has_stages(out):
            out["progression_order"] = "from_stages"
    return out


def _has_stages(data: Dict[str, Any]) -> bool:
    disease = data.get("disease") or data.get("diseases")
    if not isinstance(disease, dict):
        return False
    for g in disease.get("groups") or []:
        if isinstance(g, dict) and g.get("stages"):
            return True
    return False


def _uses_mc_gene_fc_profile(data: Dict[str, Any]) -> bool:
    """MC + DMP/gene FeatureCuts stability (analyte-agnostic; regulatory lives in manifest)."""
    sc = data.get("step_config")
    if isinstance(sc, dict):
        val = sc.get("validation")
        if isinstance(val, dict) and val.get("run_stability") and val.get("stability_gene_featurecuts_enabled"):
            return True
    name = str(data.get("project_name", ""))
    return name in ("Buffy_healthy_vs_PCa", "Plasma_healthy_vs_PCa")


def suggest_profile_name(data: Dict[str, Any]) -> str:
    if _uses_mc_gene_fc_profile(data):
        return "mc_gene_fc"
    name = str(data.get("project_name", "study"))
    if "PCa1" in name or "Healthy_vs_PCa" in name:
        return "staged_ovr_mc"
    return "discovery_gene_featurecuts"


def migrate_file(path: Path, *, in_place: bool = False, write_site: Path | None = None) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "step_config" not in raw:
        return {"status": "skipped", "reason": "no step_config"}

    step_config = dict(raw.get("step_config") or {})
    site, action_config = extract_site_and_profile(step_config)
    slim = slim_manifest(raw)
    profile_name = suggest_profile_name(raw)

    report = {
        "source": str(path),
        "profile_suggestion": profile_name,
        "site_keys": list(site.keys()),
        "action_config_sections": sorted(action_config.keys()),
    }

    out_manifest = path if in_place else path.with_name(path.stem + "_migrated.json")
    out_manifest.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
    report["manifest"] = str(out_manifest)

    profile_path = path.parent / f"{profile_name}.profile.json"
    if not profile_path.is_file():
        profile_doc = {"pipelineProfile": profile_name, "actionConfig": action_config}
        profile_path.write_text(json.dumps(profile_doc, indent=2) + "\n", encoding="utf-8")
        report["profile_written"] = str(profile_path)

    if write_site:
        merged = {}
        if write_site.is_file():
            merged = json.loads(write_site.read_text(encoding="utf-8"))
        merged = _deep_merge(merged, site)
        write_site.parent.mkdir(parents=True, exist_ok=True)
        write_site.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        report["site"] = str(write_site)

    bak = path.with_suffix(path.suffix + ".legacy.bak")
    if in_place and not bak.is_file():
        bak.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        report["backup"] = str(bak)

    return report


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Legacy project JSON file(s)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite manifest (writes .legacy.bak)")
    parser.add_argument(
        "--site-out",
        type=Path,
        default=Path("/work/site/methyl_site.json"),
        help="Merge extracted site keys into this path",
    )
    args = parser.parse_args(argv)

    for p in args.paths:
        path = Path(p)
        if not path.is_file():
            print(f"skip missing: {path}", file=sys.stderr)
            continue
        report = migrate_file(path, in_place=args.in_place, write_site=args.site_out)
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
