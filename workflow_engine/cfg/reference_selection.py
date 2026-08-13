"""Resolve site ``reference_selection`` pins into concrete genome paths."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Union

# Filenames for the current selected pins (operators change pins, not code defaults
# for science knobs — these are inventory layout conventions for materialize).
LINEAR_FASTA_NAME = "Homo_sapiens.GRCh38.dna.primary_assembly.fa"
# MojoFq2bamMeth dense-v1 pack siblings (default k=15). Shipped under the same
# linear/GRCh38/ensembl-114/ prefix as the FASTA; Phase 0 s3_sync pulls them.
LINEAR_MOJO_K = 15
GENCODE_GTF_NAME = "gencode.v49.annotation.gtf"
PANGENOME_FILES = {
    "gbz": "hprc-v1.1-mc-grch38.d9.gbz",
    "dist": "hprc-v1.1-mc-grch38.d9.autoindex.1.70.dist",
    "min": "hprc-v1.1-mc-grch38.d9.autoindex.1.70.shortread.withzip.min",
    "zipcodes": "hprc-v1.1-mc-grch38.d9.autoindex.1.70.shortread.zipcodes",
    "ref_paths": "hprc-v1.1-mc-grch38.d9.paths.sub",
}

# Map reference_selection keys → cfg.site_reference_asset.asset_role.
# pangenome_wgbs_bundle is the inventory asset_type only: ck_cfg_sra_role has
# no WGBS role, and uq_cfg_sra_site_role allows one pangenome_bundle per site.
# Site SQL seed links d9-1.70; swap d9-bs-1.70 in @links for a WGBS site.
SELECTION_TO_ASSET_ROLE = {
    "linear": "reference_genome",
    "gene_annotation": "annotation_gtf",
    "pangenome": "pangenome_bundle",
    "pangenome_wgbs": "pangenome_wgbs_bundle",
    "houseman_seed": "houseman_seed_basis",
    "hitimed_hierarchy": "hitimed_hierarchy_basis",
}

# Selection keys that resolve to cfg.reference_asset inventory (genomes on QNAP).
GENOME_SELECTION_KEYS = ("linear", "gene_annotation", "pangenome", "pangenome_wgbs")

# Default filenames for the methylGrapher BS bundle under d9-bs/1.70
# (native methylGrapher / vg autoindex output names on QNAP).
PANGENOME_WGBS_FILES = {
    "c2t_gbz": "hprc-d9-bs.wl.C2T.giraffe.gbz",
    "c2t_dist": "hprc-d9-bs.wl.C2T.dist",
    "c2t_min": "hprc-d9-bs.wl.C2T.shortread.withzip.min",
    "c2t_zipcodes": "hprc-d9-bs.wl.C2T.shortread.zipcodes",
    "g2a_gbz": "hprc-d9-bs.wl.G2A.giraffe.gbz",
    "g2a_dist": "hprc-d9-bs.wl.G2A.dist",
    "g2a_min": "hprc-d9-bs.wl.G2A.shortread.withzip.min",
    "g2a_zipcodes": "hprc-d9-bs.wl.G2A.shortread.zipcodes",
    "cpg_tsv": "hprc-d9-bs.cpg.tsv",
    # Copied from stock d9/1.70 into the BS prefix for self-contained sync.
    "ref_paths": "hprc-v1.1-mc-grch38.d9.paths.sub",
    "node_replacement_json": "hprc-d9-bs.wl.node.replacement.json",
    # PrepareGenome original graph — required by methylGrapher MethylCall.
    "wl_gfa": "hprc-d9-bs.wl.gfa",
}


def genomes_root(work_root: Path | str) -> Path:
    return Path(work_root) / "genomes"


def normalize_inventory_prefix(value: str) -> str:
    """Normalize pin / inventoryPrefix / recipe key for comparison."""
    return str(value or "").strip().strip("/")


def asset_inventory_prefix(document: Mapping[str, Any]) -> Optional[str]:
    """Return inventory prefix from a reference_asset document (or recipe key)."""
    raw = document.get("inventoryPrefix") or document.get("inventory_prefix")
    if raw:
        return normalize_inventory_prefix(str(raw))
    recipe = document.get("recipe") or {}
    for step in recipe.get("steps") or []:
        if not isinstance(step, Mapping):
            continue
        op = str(step.get("op") or "").strip().lower()
        if op not in ("s3_sync", "download"):
            continue
        key = step.get("key") or step.get("prefix")
        if key:
            # download keys may include a filename; use parent dir as prefix when needed
            key_s = normalize_inventory_prefix(str(key))
            if op == "download" and "." in Path(key_s).name:
                parent = str(Path(key_s).parent).replace("\\", "/")
                if parent and parent != ".":
                    return normalize_inventory_prefix(parent)
            return key_s
    return None


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

    wgbs_rel = sel.get("pangenome_wgbs")
    if wgbs_rel:
        wgbs_dir = root / wgbs_rel
        wgbs = dict(out.get("pangenome_wgbs_genome") or {})
        # Nested c2t/g2a + scalars used by resolve_methylgrapher_wgbs_genome.
        c2t = dict(wgbs.get("c2t") or {})
        g2a = dict(wgbs.get("g2a") or {})
        for key, fname in PANGENOME_WGBS_FILES.items():
            path = str(wgbs_dir / fname)
            if key.startswith("c2t_"):
                nested_key = key[len("c2t_") :]
                if overwrite or not c2t.get(nested_key):
                    c2t[nested_key] = path
            elif key.startswith("g2a_"):
                nested_key = key[len("g2a_") :]
                if overwrite or not g2a.get(nested_key):
                    g2a[nested_key] = path
            else:
                if overwrite or not wgbs.get(key):
                    wgbs[key] = path
        wgbs["c2t"] = c2t
        wgbs["g2a"] = g2a
        if overwrite or not wgbs.get("index_prefix"):
            wgbs["index_prefix"] = str(wgbs_dir / "hprc-d9-bs")
        linear_fasta = (out.get("reference_genome") or {}).get("fasta")
        if overwrite or not wgbs.get("linear_ref_fasta"):
            if linear_fasta:
                wgbs["linear_ref_fasta"] = linear_fasta
        out["pangenome_wgbs_genome"] = wgbs
        # Also bake into actionConfig.methylgrapher_wgbs for worker resolvedConfig.
        ac = dict(out.get("actionConfig") or {})
        mg = dict(ac.get("methylgrapher_wgbs") or {})
        for key, val in wgbs.items():
            if key in ("c2t", "g2a") or (overwrite or not mg.get(key)):
                if key in ("c2t", "g2a"):
                    nested = dict(mg.get(key) or {})
                    nested.update(val)
                    mg[key] = nested
                elif overwrite or not mg.get(key):
                    mg[key] = val
        ac["methylgrapher_wgbs"] = mg
        out["actionConfig"] = ac

    return out


def _iter_published_assets(
    published_assets: Union[
        Sequence[Any],
        Mapping[str, Mapping[str, Any]],
        Iterable[Any],
    ],
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(published_assets, Mapping):
        for name, doc in published_assets.items():
            yield str(name), doc
        return
    for rec in published_assets:
        if hasattr(rec, "name") and hasattr(rec, "document"):
            yield str(rec.name), rec.document or {}
        elif isinstance(rec, Mapping) and "name" in rec:
            body = {k: v for k, v in rec.items() if k != "name"}
            yield str(rec["name"]), body
        else:
            raise TypeError(
                f"Unsupported published asset entry: {type(rec)!r}; "
                "expected store record or name→document mapping"
            )


def resolve_asset_name_for_prefix(
    pin: str,
    published_assets: Union[
        Sequence[Any],
        Mapping[str, Mapping[str, Any]],
        Iterable[Any],
    ],
) -> Optional[str]:
    """Find published reference_asset name whose inventory prefix matches ``pin``."""
    want = normalize_inventory_prefix(pin)
    if not want:
        return None
    matches: list[str] = []
    for name, doc in _iter_published_assets(published_assets):
        prefix = asset_inventory_prefix(doc)
        if prefix and prefix == want:
            matches.append(name)
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"multiple reference_asset rows match inventory prefix {want!r}: {matches}"
        )
    return matches[0]


def selected_asset_names(
    site_doc: Dict[str, Any],
    published_assets: Union[
        Sequence[Any],
        Mapping[str, Mapping[str, Any]],
        Iterable[Any],
    ],
) -> Dict[str, str]:
    """Return selection_key → reference_asset name by matching pin path to inventoryPrefix.

    Pins under ``reference_selection`` (e.g. ``linear/GRCh38/ensembl-114``) must match
    a published asset's ``inventoryPrefix`` (or recipe ``s3_sync``/``download`` key).
    Raises ``ValueError`` when a genome pin is set but no published asset matches.
    """
    sel = site_doc.get("reference_selection") or {}
    out: Dict[str, str] = {}
    for key in GENOME_SELECTION_KEYS:
        pin = sel.get(key)
        if not pin:
            continue
        name = resolve_asset_name_for_prefix(str(pin), published_assets)
        if name is None:
            raise ValueError(
                f"reference_selection.{key}={pin!r} does not match any published "
                "reference_asset inventoryPrefix (publish the asset or fix the pin)."
            )
        out[key] = name
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
    wgbs = resolved.get("pangenome_wgbs_genome") or {}
    if wgbs:
        # original_gbz is optional (surject falls back to C2T). wl.gfa is required
        # for MethylCall and is part of PANGENOME_WGBS_FILES.
        for key in ("ref_paths", "cpg_tsv", "linear_ref_fasta", "wl_gfa"):
            checks.append(wgbs.get(key))
        if wgbs.get("node_replacement_json"):
            checks.append(wgbs.get("node_replacement_json"))
        for side in ("c2t", "g2a"):
            nested = wgbs.get(side) or {}
            if isinstance(nested, Mapping):
                for key in ("gbz", "dist", "min", "zipcodes"):
                    checks.append(nested.get(key))
    for path_s in checks:
        if not path_s:
            continue
        p = Path(path_s)
        if p.is_file():
            present.append(str(p))
        else:
            missing.append(str(p))

    # Mojo linear dense-v1 pack (required when linear pin is set).
    # Skip when METHYL_REQUIRE_MOJO_LINEAR=0 (legacy / partial trees).
    require_mojo = os.environ.get("METHYL_REQUIRE_MOJO_LINEAR", "1").strip().lower()
    if require_mojo not in ("0", "false", "no", "off"):
        fasta_s = (resolved.get("reference_genome") or {}).get("fasta")
        if fasta_s:
            fasta_p = Path(fasta_s)
            c2t = Path(str(fasta_p) + ".C2T.fa")
            pack = Path(str(fasta_p) + f".mojo_linear_k{LINEAR_MOJO_K}")
            for path_s in (
                str(c2t),
                str(pack / "meta.json"),
                str(pack / "kmers.bin"),
                str(pack / "offsets.bin"),
                str(pack / "postings.bin"),
            ):
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
