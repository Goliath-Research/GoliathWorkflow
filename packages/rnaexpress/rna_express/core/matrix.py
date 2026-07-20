"""Cohort expression matrix loader (samples x genes), RNA analogue of the methylation
fraction extractor used by the tabular sklearn backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import h5py
import numpy as np

from .expression_store import find_expression_h5


def _read_h5(path: Path) -> Tuple[List[str], np.ndarray]:
    with h5py.File(path, "r") as h5:
        gene_ids = [g.decode() if isinstance(g, bytes) else str(g) for g in h5["gene_id"][:]]
        counts = np.asarray(h5["count"][:], dtype=np.float64)
    return gene_ids, counts


def load_expression_matrix(
    sample_paths: Sequence[str | Path],
    *,
    gene_order: Optional[Sequence[str]] = None,
    transform: str = "logcpm",
    min_total_count: float = 1.0,
) -> Tuple[np.ndarray, List[str], List[str]]:
    """Stack per-sample ``expression.h5`` into a dense ``samples x genes`` matrix.

    Parameters
    ----------
    sample_paths: sample directories (or direct expression.h5 paths).
    gene_order: optional fixed gene panel (columns); when omitted the union of genes
        across samples is used, sorted for determinism.
    transform: ``logcpm`` (log2(CPM+1)), ``cpm``, or ``count`` (raw).

    Returns (X, gene_ids, sample_ids). Missing genes for a sample are 0.
    """
    resolved: List[Tuple[str, Path]] = []
    for sp in sample_paths:
        h5 = find_expression_h5(sp)
        if h5 is None:
            raise RuntimeError(f"no expression.h5 under {sp}")
        sample_id = h5.name[: -len(".expression.h5")]
        resolved.append((sample_id, h5))

    per_sample: List[Tuple[str, List[str], np.ndarray]] = []
    gene_set = set()
    for sample_id, h5 in resolved:
        genes, counts = _read_h5(h5)
        per_sample.append((sample_id, genes, counts))
        gene_set.update(genes)

    if gene_order is not None:
        genes_out = [str(g) for g in gene_order]
    else:
        genes_out = sorted(gene_set)
    col_index = {g: j for j, g in enumerate(genes_out)}

    n_samples = len(per_sample)
    n_genes = len(genes_out)
    X = np.zeros((n_samples, n_genes), dtype=np.float64)
    sample_ids: List[str] = []
    for i, (sample_id, genes, counts) in enumerate(per_sample):
        sample_ids.append(sample_id)
        for g, c in zip(genes, counts):
            j = col_index.get(g)
            if j is not None:
                X[i, j] = c

    if transform in ("cpm", "logcpm"):
        lib = X.sum(axis=1, keepdims=True)
        lib[lib < min_total_count] = min_total_count
        cpm = X / lib * 1e6
        if transform == "logcpm":
            X = np.log2(cpm + 1.0)
        else:
            X = cpm
    elif transform != "count":
        raise ValueError(f"unknown transform: {transform!r}")

    return X.astype(np.float64), genes_out, sample_ids
