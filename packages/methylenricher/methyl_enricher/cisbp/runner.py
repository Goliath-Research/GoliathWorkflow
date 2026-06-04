"""
Entry point that dispatches a CIS-BP run to the configured mode handler.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Set

from .registry import get_mode_handler

logger = logging.getLogger(__name__)


@dataclass
class CisbpContext:
    """Runtime context passed to CIS-BP mode handlers."""

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".methyl_enricher")
    gtf: Optional[str] = None
    genome_fasta: Optional[str] = None
    gene_universe: Optional[Set[str]] = None
    dmp_detection_dir: Optional[str] = None
    background: Optional[int] = None
    cutoff: float = 0.05

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)


def run_cisbp(
    cfg,
    genes: Sequence[str],
    output_dir,
    context: Optional[CisbpContext] = None,
) -> Optional[str]:
    """
    Run the configured CIS-BP integration mode.

    Returns the library label to merge into enrichment results, or ``None`` when
    disabled or nothing was produced. Raises for genuine misconfiguration so the
    caller can surface it; the caller (EnrichmentAnalyzer) decides whether to
    treat failures as soft.
    """
    if cfg is None or not getattr(cfg, "enabled", False):
        return None
    context = context or CisbpContext()
    mode = (cfg.mode or "gene_sets").strip().lower()
    handler = get_mode_handler(mode)
    logger.info("[CIS-BP] running mode '%s' (label=%s)", mode, cfg.label or "CIS-BP")
    return handler(cfg, genes, Path(output_dir), context)
