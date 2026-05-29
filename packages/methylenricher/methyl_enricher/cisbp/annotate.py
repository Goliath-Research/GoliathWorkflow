"""
Mode 1B (planned): annotate result TFs with CIS-BP motif metadata.

This would take TFs already surfaced by Enrichr ChEA/ENCODE/TRRUST results and
attach CIS-BP metadata (motif IDs, TF family, Direct/Inferred evidence, species)
as a complementary output. The CIS-BP bundle loader and TF_Information parsing
(see ``download.CisbpBundle.load_tf_info``) already provide the needed data; this
handler is intentionally left as a stub until prioritized.
"""

from __future__ import annotations

from typing import Optional, Sequence


def run(cfg, genes: Sequence[str], output_dir, context) -> Optional[str]:  # noqa: ANN001
    raise NotImplementedError(
        "CIS-BP mode 'annotate' (1B) is planned but not implemented yet. "
        "Use cisbp.mode='gene_sets' for now."
    )
