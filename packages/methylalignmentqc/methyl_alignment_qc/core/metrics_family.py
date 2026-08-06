"""Detect alignment QC metrics family (Parabricks vs methylGrapher WGBS)."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class MetricsFamily(str, Enum):
    PARABRICKS = "parabricks"
    METHYLGRAPHER_WGBS = "methylgrapher_wgbs"


_WGBS_MODES = frozenset({"pangenome_wgbs", "wgbs_pangenome", "methylgrapher_wgbs"})
_PARABRICKS_MODES = frozenset({"linear", "pangenome", "fq2bam", "giraffe"})


def normalize_alignment_mode(alignment_mode: Optional[str]) -> Optional[str]:
    if alignment_mode is None:
        return None
    mode = str(alignment_mode).strip().lower()
    return mode or None


def find_alignment_metrics_json(sample_dir: Path, sample_name: str) -> Optional[Path]:
    candidate = Path(sample_dir) / f"{sample_name}.alignment_metrics.json"
    return candidate if candidate.is_file() else None


def load_alignment_metrics_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"alignment_metrics.json must be an object: {path}")
    return raw


def is_methylgrapher_provenance(raw: Dict[str, Any]) -> bool:
    tool = str(raw.get("tool") or "").lower()
    return "methylgrapher" in tool or str(raw.get("action") or "").startswith(
        "sample.methylgrapher"
    )


def detect_metrics_family(
    sample_dir: Path,
    sample_name: str,
    *,
    alignment_mode: Optional[str] = None,
    parabricks_available: bool = False,
) -> Tuple[MetricsFamily, Optional[Path], Optional[Dict[str, Any]]]:
    """
    Resolve metrics family for a sample directory.

    Returns ``(family, provenance_path_or_none, provenance_dict_or_none)``.

    When ``alignment_mode`` is ``pangenome_wgbs``, never treat a stale linear
    Picard tar / stub JSON as the metrics source — require methylGrapher provenance.
    """
    sample_dir = Path(sample_dir)
    mode = normalize_alignment_mode(alignment_mode)
    prov_path = find_alignment_metrics_json(sample_dir, sample_name)
    prov: Optional[Dict[str, Any]] = None
    if prov_path is not None:
        try:
            prov = load_alignment_metrics_json(prov_path)
        except (OSError, ValueError, json.JSONDecodeError):
            prov = None

    if mode in _WGBS_MODES:
        if prov is None or not is_methylgrapher_provenance(prov):
            raise RuntimeError(
                f"alignmentMode={mode} requires {sample_name}.alignment_metrics.json "
                f"with tool=methylGrapher under {sample_dir} "
                "(refusing stale linear/Parabricks qc-metrics fallback)"
            )
        return MetricsFamily.METHYLGRAPHER_WGBS, prov_path, prov

    if mode in _PARABRICKS_MODES:
        if not parabricks_available:
            raise RuntimeError(
                f"alignmentMode={mode} requires Parabricks/Picard metrics "
                f"({sample_name}.json or Picard tables in {sample_name}.qc-metrics.tar)"
            )
        return MetricsFamily.PARABRICKS, None, None

    # Infer from artifacts when mode omitted
    if prov is not None and is_methylgrapher_provenance(prov) and not parabricks_available:
        return MetricsFamily.METHYLGRAPHER_WGBS, prov_path, prov
    if parabricks_available:
        return MetricsFamily.PARABRICKS, None, None
    if prov is not None and is_methylgrapher_provenance(prov):
        return MetricsFamily.METHYLGRAPHER_WGBS, prov_path, prov

    raise RuntimeError(
        f"Missing Parabricks metrics for {sample_name}: expected a full "
        f"{sample_dir / f'{sample_name}.json'} or "
        f"{sample_dir / f'{sample_name}.qc-metrics.tar'} "
        f"(or methylGrapher {sample_name}.alignment_metrics.json for pangenome_wgbs)"
    )
