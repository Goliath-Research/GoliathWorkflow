"""
Mode 1C (planned): motif enrichment over DMP/DMR genomic regions.

This would scan differentially-methylated region sequences (rather than gene
promoters) with CIS-BP PWMs and test for over-represented TF motifs around the
methylation signal. It reuses the same scanning core as mode 1A
(``pwm.best_relative_score`` + the CIS-BP bundle); only the sequence source and
the statistical model differ. Left as a stub until prioritized.
"""

from __future__ import annotations

from typing import Optional, Sequence


def run(cfg, genes: Sequence[str], output_dir, context) -> Optional[str]:  # noqa: ANN001
    raise NotImplementedError(
        "CIS-BP mode 'motif_scan' (1C) is planned but not implemented yet. "
        "Use cisbp.mode='gene_sets' for now."
    )
