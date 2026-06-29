"""Engine defaults for gene FeatureCuts resource caps."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple, Union
from pathlib import Path
import json

DEFAULT_GENE_FEATURECUTS_MAX_DMPS = 1000
DEFAULT_GENE_FEATURECUTS_MAX_GENES = 200


def apply_gene_featurecuts_cap_defaults(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Fill missing gene FC caps with engine defaults (in-place copy)."""
    out = dict(mapping)
    if out.get("stability_gene_featurecuts_max_dmps") is None:
        out["stability_gene_featurecuts_max_dmps"] = DEFAULT_GENE_FEATURECUTS_MAX_DMPS
    if out.get("stability_gene_featurecuts_max_genes") is None:
        out["stability_gene_featurecuts_max_genes"] = DEFAULT_GENE_FEATURECUTS_MAX_GENES
    if out.get("max_dmps") is None:
        out["max_dmps"] = out["stability_gene_featurecuts_max_dmps"]
    if out.get("max_genes") is None:
        out["max_genes"] = out["stability_gene_featurecuts_max_genes"]
    return out


def load_mc_config_gene_caps(run_dir: Union[str, Path]) -> Dict[str, Any]:
    """Read gene FC caps from ``monte_carlo_runs/queue/mc_config.json`` when present."""
    rd = Path(run_dir)
    mc_root = rd.parent if rd.name.startswith("run_") else rd
    path = mc_root / "queue" / "mc_config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def resolve_gene_featurecuts_caps(
    *,
    max_genes: Optional[int] = None,
    max_dmps: Optional[int] = None,
    resolved_config: Optional[Mapping[str, Any]] = None,
    run_dir: Optional[Union[str, Path]] = None,
) -> Tuple[int, int]:
    """Resolve gene FC caps from task input, resolved profile, MC snapshot, then defaults."""
    genes = max_genes
    dmps = max_dmps

    resolved = dict(resolved_config or {})
    if genes is None:
        genes = resolved.get("max_genes") or resolved.get("stability_gene_featurecuts_max_genes")
    if dmps is None:
        dmps = resolved.get("max_dmps") or resolved.get("stability_gene_featurecuts_max_dmps")

    if run_dir is not None and (genes is None or dmps is None):
        mc = load_mc_config_gene_caps(run_dir)
        if genes is None:
            genes = mc.get("stability_gene_featurecuts_max_genes") or mc.get("gene_featurecuts_max_genes")
        if dmps is None:
            dmps = mc.get("stability_gene_featurecuts_max_dmps")

    applied = apply_gene_featurecuts_cap_defaults(
        {
            "stability_gene_featurecuts_max_genes": genes,
            "stability_gene_featurecuts_max_dmps": dmps,
        }
    )
    return (
        int(applied["stability_gene_featurecuts_max_genes"]),
        int(applied["stability_gene_featurecuts_max_dmps"]),
    )
