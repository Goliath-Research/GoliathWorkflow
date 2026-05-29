"""
Shared resolution of the CIS-BP config + runtime context from a project.

Both the CLI (`cli.py`) and the ensure-complete/freeze path (`ensure_complete.py`)
use these helpers so CIS-BP behaves identically regardless of entry point.

Defaults follow the project's existing properties:
  * genome_fasta <- step_config.alignment_qc.genome_fasta
  * gtf          <- step_config.mapper.gtf  (then GENE_GTF env)
  * cache_dir    <- step_config.enricher.methyl_enricher_home (project resolver)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .runner import CisbpContext

_GENOME_FASTA_ENV = ("CISBP_GENOME_FASTA", "GENOME_FASTA")


def effective_cisbp_config(enricher_config) -> Optional[object]:
    """
    Build the effective CisbpConfig from an EnricherStepConfig, merging the
    nested ``cisbp`` object with the flat ``cisbp_enabled`` / ``cisbp_mode``
    quick-toggles. Returns ``None`` when CIS-BP is not configured at all.
    """
    from ..config import CisbpConfig

    cfg = getattr(enricher_config, "cisbp", None)
    enabled_flat = getattr(enricher_config, "cisbp_enabled", None)
    mode_flat = getattr(enricher_config, "cisbp_mode", None)

    if cfg is None and (enabled_flat is not None or mode_flat is not None):
        cfg = CisbpConfig()
    if cfg is None:
        return None

    updates = {}
    if enabled_flat is not None:
        updates["enabled"] = enabled_flat
    if mode_flat is not None:
        updates["mode"] = mode_flat
    if updates:
        cfg = cfg.model_copy(update=updates)
    return cfg


def resolve_cisbp_context(
    cisbp_config,
    *,
    project=None,
    project_path=None,
    cutoff: float = 0.05,
    cache_dir: Optional[str] = None,
) -> CisbpContext:
    """Resolve cache dir, GTF, genome FASTA and gene universe for CIS-BP."""
    cd = cache_dir or getattr(cisbp_config, "cache_dir", None)
    if not cd and project_path is not None:
        try:
            from ..project_resolver import resolve_methyl_enricher_home

            cd = resolve_methyl_enricher_home(project_path)
        except Exception:
            cd = None
    if not cd:
        cd = str(Path.home() / ".methyl_enricher")

    gtf = getattr(cisbp_config, "gtf", None)
    if not gtf and project is not None:
        try:
            gtf = (project.get_step_config("mapper") or {}).get("gtf")
        except Exception:
            gtf = None
    if not gtf:
        gtf = os.environ.get("GENE_GTF")

    # Genome FASTA defaults to the project's shared reference in
    # step_config.alignment_qc.genome_fasta (cisbp.genome_fasta overrides it).
    genome_fasta = getattr(cisbp_config, "genome_fasta", None)
    if not genome_fasta and project is not None:
        try:
            genome_fasta = (project.get_step_config("alignment_qc") or {}).get("genome_fasta")
        except Exception:
            genome_fasta = None
    if not genome_fasta:
        for env_key in _GENOME_FASTA_ENV:
            if os.environ.get(env_key):
                genome_fasta = os.environ[env_key]
                break

    gene_universe = None
    universe_file = getattr(cisbp_config, "gene_universe_file", None)
    if universe_file and Path(universe_file).is_file():
        with open(universe_file, encoding="utf-8") as fh:
            gene_universe = {ln.strip() for ln in fh if ln.strip()}

    return CisbpContext(
        cache_dir=cd,
        gtf=gtf,
        genome_fasta=genome_fasta,
        gene_universe=gene_universe,
        background=getattr(cisbp_config, "background_size", None),
        cutoff=cutoff,
    )
