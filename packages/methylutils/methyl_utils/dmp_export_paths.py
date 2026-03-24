"""
Resolve DMP CSV paths for dual-branch exports (discovery vs classifier).

MethylDetector ``dmp_export_mode=dual`` writes:
  - ``dmps-{chrom}-discovery.csv`` — mapper / enricher / interpretation
  - ``dmps-{chrom}-classifier.csv`` — prediction panel (matches classifier pickle positions)

Unified mode writes a single ``dmps-{chrom}.csv`` (classifier panel; may be widened for mapper).
"""

from __future__ import annotations

from pathlib import Path
from typing import List


def find_classifier_dmps_csvs(detection_dir: Path) -> List[Path]:
    """
    Per-chromosome classifier / prediction DMP tables for multiclass merge and similar tools.

    Prefers ``dmps-*-classifier.csv`` when present; otherwise legacy ``dmps-*.csv`` excluding
    ``*-discovery`` stems.
    """
    if not detection_dir.exists():
        return []
    classifier = sorted(detection_dir.glob("dmps-*-classifier.csv"))
    if classifier:
        return classifier
    out: List[Path] = []
    for p in sorted(detection_dir.glob("dmps-*.csv")):
        stem = p.stem
        if stem.endswith("-discovery"):
            continue
        out.append(p)
    return out


def find_discovery_dmps_csvs(detection_dir: Path) -> List[Path]:
    """DMP tables intended for MethylMapper / MethylEnricher (broad lists)."""
    if not detection_dir.exists():
        return []
    disc = sorted(detection_dir.glob("dmps-*-discovery.csv"))
    if disc:
        return disc
    # Unified mode: same file serves both roles
    return find_classifier_dmps_csvs(detection_dir)


def first_classifier_dmps_csv(detection_dir: Path) -> Path | None:
    csvs = find_classifier_dmps_csvs(detection_dir)
    return csvs[0] if csvs else None
