"""
Baselines and per-run override JSON (split from CLI to avoid import cycles with planner/queue).
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .validator_metrics import metrics_schema_descriptor

if TYPE_CHECKING:
    from .config import MonteCarloConfig


def digest_sample_paths(paths: List[str]) -> str:
    h = hashlib.sha256()
    for p in sorted(str(x) for x in paths):
        h.update(p.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def write_baseline_manifest(
    *,
    output_root: Path,
    mode: str,
    config: "MonteCarloConfig",
    layout: str,
    cohort_paths_list: List[Tuple[str, List[str]]],
    split_reuse_source_root: Optional[Path] = None,
) -> Path:
    reg = getattr(config, "regulatory", None)
    vp = getattr(config, "validation_partitions", None)
    roles_present = []
    roles_missing = []
    if vp is not None:
        for role in (
            "development_train",
            "internal_validation",
            "locked_test",
            "pivotal_validation",
            "post_market_monitoring",
        ):
            vals = list(getattr(vp, role, []) or [])
            if vals:
                roles_present.append(role)
            else:
                roles_missing.append(role)
    payload: Dict[str, Any] = {
        "manifest_version": "probabilistic_v2_baseline_v1",
        "mode": str(mode),
        "layout": str(layout),
        "n_iterations": int(config.n_iterations),
        "train_fraction": float(config.train_fraction),
        "seed_policy": {
            "base_seed": int(config.seed) if config.seed is not None else None,
            "per_iteration_seed_rule": "seed_i = base_seed + iteration_index",
            "split_strategy": "stratified_per_cohort",
        },
        "cohorts": [
            {
                "label": str(label),
                "n_samples": int(len(paths)),
                "sample_digest_sha256": digest_sample_paths(paths),
            }
            for label, paths in cohort_paths_list
        ],
        "metrics_schema": metrics_schema_descriptor(),
        "regulatory": {
            "stage": getattr(reg, "stage", "feasibility"),
            "allow_clinical_performance_claims": bool(
                getattr(reg, "allow_clinical_performance_claims", False)
            ),
            "claim_boundary": getattr(reg, "claim_boundary", None),
            "intended_use_summary": getattr(reg, "intended_use_summary", None),
            "target_population": getattr(reg, "target_population", None),
            "sample_type": getattr(reg, "sample_type", None),
            "reference_standard": getattr(reg, "reference_standard", None),
        },
        "validation_partitions": {
            "configured": vp is not None,
            "roles_present": roles_present,
            "roles_missing": roles_missing,
            "independence_keys": list(getattr(vp, "independence_keys", []) or []),
        },
    }
    if split_reuse_source_root is not None:
        payload["split_reuse"] = {
            "policy": "auto_try_primary_runs_then_stratified",
            "candidate_source_root": str(Path(split_reuse_source_root).resolve()),
            "run_id_pattern": "run_{iteration:04d} for iteration 1..n_iterations",
        }
    output_root.mkdir(parents=True, exist_ok=True)
    out = output_root / "baseline_manifest.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out


def write_detector_featurecuts_override(
    run_dir: Path,
    config: "MonteCarloConfig",
) -> Optional[Path]:
    enable_featurecuts = bool(config.stability_featurecuts_enabled)
    target_ba = config.stability_target_balanced_accuracy
    min_selected_dmps = config.stability_min_selected_dmps
    if not enable_featurecuts and target_ba is None and min_selected_dmps is None:
        return None

    payload: Dict[str, Any] = {}
    if enable_featurecuts or target_ba is not None or min_selected_dmps is not None:
        payload["classifier_dmp_selection"] = "featurecuts_validation"
    if target_ba is not None:
        payload["target_balanced_accuracy"] = float(target_ba)
    if min_selected_dmps is not None:
        payload["min_selected_dmps"] = int(min_selected_dmps)
    if not payload:
        return None
    out = run_dir / "detector_step_override.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out
