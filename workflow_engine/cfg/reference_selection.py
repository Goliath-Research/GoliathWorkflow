"""Resolve site ``reference_selection`` pins into concrete genome paths."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

# Filenames for the current selected pins (operators change pins, not code defaults
# for science knobs — these are inventory layout conventions for materialize).
LINEAR_FASTA_NAME = "Homo_sapiens.GRCh38.dna.primary_assembly.fa"
GENCODE_GTF_NAME = "gencode.v49.annotation.gtf"
PANGENOME_FILES = {
    "gbz": "hprc-v1.1-mc-grch38.d9.gbz",
    "dist": "hprc-v1.1-mc-grch38.d9.autoindex.1.70.dist",
    "min": "hprc-v1.1-mc-grch38.d9.autoindex.1.70.shortread.withzip.min",
    "zipcodes": "hprc-v1.1-mc-grch38.d9.autoindex.1.70.shortread.zipcodes",
    "ref_paths": "hprc-v1.1-mc-grch38.d9.paths.sub",
}

# Map reference_selection keys → cfg.site_reference_asset.asset_role
SELECTION_TO_ASSET_ROLE = {
    "linear": "reference_genome",
    "gene_annotation": "annotation_gtf",
    "pangenome": "pangenome_bundle",
    "houseman_seed": "houseman_seed_basis",
    "hitimed_hierarchy": "hitimed_hierarchy_basis",
}

# Map selection key → published reference_asset name (seed fixtures)
SELECTION_TO_ASSET_NAME = {
    "linear": "linear-grch38-ensembl-114",
    "gene_annotation": "gencode-v49",
    "pangenome": "pangenome-grch38-d9-1.70",
}


def genomes_root(work_root: Path | str) -> Path:
    return Path(work_root) / "genomes"


def apply_reference_selection(
    site_doc: Dict[str, Any],
    *,
    work_root: Path | str = "/work",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Fill ``reference_genome`` / ``annotation`` / ``pangenome_genome`` from
    ``reference_selection`` when concrete paths are missing (or always if
    ``overwrite``).
    """
    out = deepcopy(site_doc)
    sel = out.get("reference_selection") or {}
    root = genomes_root(work_root)

    linear_rel = sel.get("linear")
    if linear_rel:
        fasta = root / linear_rel / LINEAR_FASTA_NAME
        ref = dict(out.get("reference_genome") or {})
        if overwrite or not ref.get("fasta"):
            ref["fasta"] = str(fasta)
        out["reference_genome"] = ref

    ann_rel = sel.get("gene_annotation")
    if ann_rel:
        # Prefer gencode.vNN.annotation.gtf matching the version directory name
        version = Path(ann_rel).name  # e.g. v49
        gtf_name = f"gencode.{version}.annotation.gtf"
        gtf = root / ann_rel / gtf_name
        ann = dict(out.get("annotation") or {})
        if overwrite or not ann.get("gtf"):
            ann["gtf"] = str(gtf)
        out["annotation"] = ann

    pan_rel = sel.get("pangenome")
    if pan_rel:
        pan_dir = root / pan_rel
        pan = dict(out.get("pangenome_genome") or {})
        for key, fname in PANGENOME_FILES.items():
            if overwrite or not pan.get(key):
                pan[key] = str(pan_dir / fname)
        linear_fasta = (out.get("reference_genome") or {}).get("fasta")
        if overwrite or not pan.get("linear_ref_fasta"):
            if linear_fasta:
                pan["linear_ref_fasta"] = linear_fasta
        out["pangenome_genome"] = pan

    return out


def selected_asset_names(site_doc: Dict[str, Any]) -> Dict[str, str]:
    """Return selection_key → reference_asset name for pinned roles present on site."""
    sel = site_doc.get("reference_selection") or {}
    out: Dict[str, str] = {}
    for key, asset_name in SELECTION_TO_ASSET_NAME.items():
        if sel.get(key):
            out[key] = asset_name
    return out


def verify_selected_paths(
    site_doc: Dict[str, Any],
    *,
    work_root: Path | str = "/work",
) -> Dict[str, Any]:
    """Check that pinned concrete paths exist on disk."""
    resolved = apply_reference_selection(site_doc, work_root=work_root, overwrite=False)
    missing = []
    present = []
    checks = [
        (resolved.get("reference_genome") or {}).get("fasta"),
        (resolved.get("annotation") or {}).get("gtf"),
    ]
    pan = resolved.get("pangenome_genome") or {}
    for key in ("gbz", "dist", "min", "zipcodes", "ref_paths", "linear_ref_fasta"):
        checks.append(pan.get(key))
    for path_s in checks:
        if not path_s:
            continue
        p = Path(path_s)
        if p.is_file():
            present.append(str(p))
        else:
            missing.append(str(p))
    return {
        "ok": not missing,
        "present": present,
        "missing": missing,
        "reference_selection": resolved.get("reference_selection") or {},
    }
