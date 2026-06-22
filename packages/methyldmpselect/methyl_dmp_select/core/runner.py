"""Run DMP panel selection from discovery CSV artifacts."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from ..models.config import DmpSelectionConfig

logger = logging.getLogger(__name__)


def _discovery_path(config: DmpSelectionConfig) -> Path:
    if config.discovery_csv:
        return Path(config.discovery_csv)
    return Path(config.output_dir) / f"dmps-{config.chromosome}-discovery.csv"


def _audit_path(config: DmpSelectionConfig) -> Path:
    return Path(config.output_dir) / f"dmp_selection-{config.chromosome}.json"


def selection_outputs_exist(config: DmpSelectionConfig) -> bool:
    out = Path(config.output_dir)
    chrom = config.chromosome
    core = out / f"dmps-{chrom}-classifier.csv"
    ext = out / f"dmps-{chrom}-classifier-extended.csv"
    audit = _audit_path(config)
    return core.is_file() and ext.is_file() and audit.is_file()


def _config_hash(config: DmpSelectionConfig) -> str:
    import hashlib

    payload = config.model_dump(mode="json")
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def run_dmp_selection(
    config: DmpSelectionConfig,
    *,
    skip_if_exists: bool = True,
) -> Dict[str, Any]:
    """
    Select classifier DMP panel from discovery CSV and write classifier exports.

    Delegates ECDF / validation math to MethylDetector selection helpers (shared centroid context).
    """
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = _audit_path(config)

    if skip_if_exists and selection_outputs_exist(config):
        logger.info("DMP selection outputs already exist for chr %s; skipping", config.chromosome)
        with open(audit_path, encoding="utf-8") as f:
            prior = json.load(f)
        return {"status": "skipped", "audit": prior}

    discovery = _discovery_path(config)
    if not discovery.is_file():
        raise FileNotFoundError(f"Discovery CSV not found: {discovery}")

    from methyl_detector.core.methyldetector import MethylDetector
    from methyl_detector.models.config import MethylDetectorConfig

    det_payload = config.model_dump(by_alias=False)
    sel_mode = det_payload.pop("selection_mode", det_payload.pop("classifier_dmp_selection", "elbow"))
    det_payload["classifier_dmp_selection"] = sel_mode
    det_payload.pop("discovery_csv", None)
    det_payload.pop("export_classifier_pickle", None)
    detector_cfg = MethylDetectorConfig(**det_payload)
    detector = MethylDetector(detector_cfg)
    detector.chromosome = str(config.chromosome)

    sorted_df = pd.read_csv(discovery)
    if sorted_df.empty:
        raise ValueError(f"Discovery CSV is empty: {discovery}")
    if "effect_size" in sorted_df.columns:
        sorted_df = sorted_df.sort_values("effect_size", ascending=False).reset_index(drop=True)

    result = detector.run_dmp_panel_selection_from_discovery(
        sorted_df,
        export_classifier_pickle=config.export_classifier_pickle,
    )

    audit = {
        "chromosome": config.chromosome,
        "config_hash": _config_hash(config),
        "discovery_csv": str(discovery),
        "n_dmps_discovery": int(len(sorted_df)),
        "n_dmps_classifier": int(result.get("n_classifier", 0)),
        "n_dmps_extended": int(result.get("n_extended", 0)),
        "classifier_panel_audit": result.get("classifier_panel_audit"),
        "featurecuts_validation_summary": result.get("featurecuts_summary"),
    }
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)

    return {"status": "ok", "audit": audit, **result}
