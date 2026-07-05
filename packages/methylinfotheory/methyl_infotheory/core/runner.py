"""Orchestrate read-level info measures and confirmation report."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from methyl_utils.core.read_level_io import discover_pattern_files

from ..config import InfoTheoryStepConfig
from .cohort_jsd import compute_cohort_jsd_records
from .confirmation import build_confirmation_report
from .sample_measures import compute_sample_readlevel_measures

logger = logging.getLogger(__name__)


def _any_pattern_files(
    samples: Sequence[Tuple[str, str, str]],
    chromosomes: Sequence[str],
    contexts: Sequence[str],
) -> bool:
    for _sid, sample_dir, _group in samples:
        if discover_pattern_files(sample_dir, chromosomes, contexts):
            return True
    return False


def _default_comparison_groups(
    samples: Sequence[Tuple[str, str, str]],
) -> Tuple[List[str], List[str], str, str]:
    labels = sorted({g for _sid, _dir, g in samples})
    if len(labels) < 2:
        return [], [], "", ""
    return (
        [d for _sid, d, g in samples if g == labels[0]],
        [d for _sid, d, g in samples if g == labels[1]],
        labels[0],
        labels[1],
    )


def run_info_measures_for_project(
    samples: Sequence[Tuple[str, str, str]],
    output_dir: Path,
    cfg: InfoTheoryStepConfig,
    *,
    project_chromosomes: Sequence[str] | None = None,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    chromosomes = [str(c) for c in (cfg.chromosomes or project_chromosomes or ["1"])]
    contexts = [str(c) for c in (cfg.contexts or ["CG"])]

    if not _any_pattern_files(samples, chromosomes, contexts):
        logger.warning(
            "No *.patterns.h5 sidecars found; skipping info_measures "
            "(enable methyl_extract.read_level and re-extract samples)"
        )
        manifest = {
            "status": "skipped",
            "reason": "no_pattern_sidecars",
            "output_csv": None,
            "confirmation_report": None,
        }
        manifest_path = output_dir / "readlevel_measures.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    rows: List[Dict[str, Any]] = []
    for sample_id, sample_dir, _group in samples:
        rows.append(
            compute_sample_readlevel_measures(
                sample_id,
                sample_dir,
                chromosomes=chromosomes,
                contexts=contexts,
                cfg=cfg,
            )
        )

    csv_path = output_dir / "readlevel_measures.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    g1_dirs, g2_dirs, g1_label, g2_label = _default_comparison_groups(samples)
    jsd_records = []
    if g1_dirs and g2_dirs:
        jsd_records = compute_cohort_jsd_records(
            g1_dirs,
            g2_dirs,
            chromosomes=chromosomes,
            contexts=contexts,
            cfg=cfg,
        )

    report = build_confirmation_report(
        jsd_records,
        dmp_panel_csv=cfg.dmp_panel_csv,
        mapper_gene_csv=cfg.mapper_gene_csv,
    )
    report["comparison"] = {"group1": g1_label, "group2": g2_label}
    report_path = output_dir / "confirmation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    manifest = {
        "status": "ok",
        "output_csv": str(csv_path.resolve()),
        "confirmation_report": str(report_path.resolve()),
        "n_samples": int(len(rows)),
        "n_columns": int(len(rows[0]) if rows else 0),
        "n_jsd_windows": int(len(jsd_records)),
        "chromosomes": chromosomes,
        "contexts": contexts,
    }
    manifest_path = output_dir / "readlevel_measures.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
