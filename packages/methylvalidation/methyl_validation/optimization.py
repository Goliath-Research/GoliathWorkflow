"""
File-driven objective J(theta) for pipeline hyperparameter search.

Reads primary ``metrics_summary.json`` or a single ``model_mc/*/metrics_summary.json``
(and optionally ``stability/stability_summary.json``) under ``monte_carlo_runs``;
optional constraints call :func:`rollout.evaluate_dual_run` against a baseline.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, Field

# Sentinel (use ObjectiveWeights.infeasible_value in results for JSON)
INFEASIBLE: float = float("-inf")


def metric_value_from_summary(summary: Dict[str, Any], metric: str, stat: str) -> float:
    """
    One scalar from ``metrics_summary.json``-style dict (``metrics`` nested or legacy top-level).
    `stat` is \"mean\" | \"median\" (p50).
    """
    node = summary.get(metric)
    if node is None and isinstance(summary.get("metrics"), dict):
        node = summary["metrics"].get(metric)
    if not isinstance(node, dict):
        raise KeyError(f"metric {metric!r} not found in summary")
    s = (stat or "mean").lower()
    if s in ("median", "p50"):
        p = (node.get("percentiles") or {}).get("p50")
        if p is None:
            raise KeyError(f"metric {metric!r} missing p50 for median")
        return float(p)
    if s == "mean":
        if "mean" not in node:
            raise KeyError(f"metric {metric!r} missing mean")
        return float(node["mean"])
    if s in node and isinstance(node[s], (int, float)):
        return float(node[s])
    raise KeyError(f"stat {stat!r} not available for {metric!r}")


def _try_metric(summary: Dict[str, Any], metric: str, stat: str) -> Optional[float]:
    try:
        return metric_value_from_summary(summary, metric, stat)
    except (KeyError, TypeError, ValueError):
        return None


class RolloutTolerances(BaseModel):
    """Same fields as :func:`rollout.evaluate_dual_run` ``tolerances``."""

    balanced_accuracy_drop_max: float = Field(default=0.005, ge=0.0)
    macro_f1_drop_max: float = Field(default=0.005, ge=0.0)
    nll_improvement_min_frac: float = Field(default=0.02, ge=0.0)
    brier_improvement_min_frac: float = Field(default=0.02, ge=0.0)
    ece_improvement_min_frac: float = Field(default=0.05, ge=0.0)


class ConstraintSet(BaseModel):
    """
    Baseline vs candidate is checked with :func:`rollout.evaluate_dual_run` (uses **mean** stats
    in summaries, same as rollout).
    """

    baseline_metrics_summary_path: Path = Field(
        ..., description="Path to reference metrics_summary.json (baseline run)"
    )
    tolerances: RolloutTolerances = Field(default_factory=RolloutTolerances)

    def check_paths(self, candidate_metrics_summary_path: Path) -> Tuple[bool, str]:
        from .rollout import evaluate_dual_run

        if not self.baseline_metrics_summary_path.is_file():
            return False, f"missing_baseline:{self.baseline_metrics_summary_path}"
        if not candidate_metrics_summary_path.is_file():
            return False, f"missing_candidate:{candidate_metrics_summary_path}"
        r = evaluate_dual_run(
            baseline_summary_path=self.baseline_metrics_summary_path,
            candidate_summary_path=candidate_metrics_summary_path,
            tolerances=self.tolerances.model_dump(),
        )
        if r.get("recommendation") == "promote":
            return True, "ok"
        checks = r.get("checks") or {}
        return False, f"rollout:{r.get('recommendation', 'hold')}|{checks}"


class ObjectiveWeights(BaseModel):
    """
    Maximize scalar J = (weighted sum of performance terms) + (optional stability rewards).

    For loss-like metrics (NLL, Brier, ECE), a **positive** weight *subtracts* ``w * value``.
    If a weighted metric is absent (e.g. no NLL in detector-only summaries), that term is skipped;
    if **required** (non-zero w for BA or macro_f1) and missing, the run is infeasible.
    """

    stat: Literal["mean", "median"] = "median"
    w_balanced_accuracy: float = 1.0
    w_macro_f1: float = 1.0
    w_nll: float = 0.0
    w_brier: float = 0.0
    w_ece: float = 0.0
    w_stability_panel: float = 0.0
    stability_panel_cap: float = Field(default=2000.0, gt=0.0)
    w_stable_genes: float = 0.0
    stability_gene_cap: float = Field(default=500.0, gt=0.0)
    min_stable_dmps: Optional[int] = None
    min_stable_genes: Optional[int] = None
    relax_min_stable: bool = False
    infeasible_value: float = Field(default=-1.0e9)


class ObjectiveResult(BaseModel):
    value: float
    feasible: bool
    reason: str = "ok"
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_json_friendly(self) -> Dict[str, Any]:
        out = self.model_dump()
        v = out.get("value")
        if isinstance(v, float) and ((math.isinf(v) and v < 0) or math.isnan(v)):
            out["value"] = float(self.details.get("infeasible_value", -1.0e9))
        return out


def _panel_reward(n: float, cap: float) -> float:
    if n <= 0.0 or cap <= 0:
        return 0.0
    return min(n, cap) / cap


def _resolve_metrics_summary(root: Path) -> Path:
    """Prefer primary MC metrics, then a single model-MC backend summary."""
    primary = root / "metrics_summary.json"
    if primary.is_file():
        return primary
    backend_summaries = sorted((root / "model_mc").glob("*/metrics_summary.json"))
    if len(backend_summaries) == 1:
        return backend_summaries[0]
    return primary


def objective_from_monte_carlo_artifacts(
    monte_carlo_runs_root: str | Path,
    weights: ObjectiveWeights,
    constraints: Optional[ConstraintSet] = None,
) -> ObjectiveResult:
    root = Path(monte_carlo_runs_root)
    ms = _resolve_metrics_summary(root)
    details: Dict[str, Any] = {
        "monte_carlo_runs_root": str(root),
        "metrics_summary_path": str(ms),
        "infeasible_value": weights.infeasible_value,
    }

    if not ms.is_file():
        return ObjectiveResult(
            value=weights.infeasible_value,
            feasible=False,
            reason="missing_metrics_summary",
            details=details,
        )

    if constraints is not None:
        ok, why = constraints.check_paths(ms)
        details["rollout_check"] = why
        if not ok:
            return ObjectiveResult(
                value=weights.infeasible_value,
                feasible=False,
                reason=why,
                details=details,
            )

    with open(ms, encoding="utf-8") as f:
        candidate = json.load(f)
    if not isinstance(candidate, dict):
        return ObjectiveResult(
            value=weights.infeasible_value,
            feasible=False,
            reason="invalid_metrics_summary",
            details=details,
        )

    stat = weights.stat
    j = 0.0
    terms: Dict[str, float] = {}

    try:
        if weights.w_balanced_accuracy:
            v = _try_metric(candidate, "balanced_accuracy", stat)
            if v is None:
                raise KeyError("balanced_accuracy")
            j += weights.w_balanced_accuracy * v
            terms["balanced_accuracy"] = v
        if weights.w_macro_f1:
            v = _try_metric(candidate, "macro_f1", stat)
            if v is None:
                raise KeyError("macro_f1")
            j += weights.w_macro_f1 * v
            terms["macro_f1"] = v
        if weights.w_nll:
            v = _try_metric(candidate, "nll", stat)
            if v is not None:
                j -= abs(weights.w_nll) * v
                terms["nll"] = v
        if weights.w_brier:
            v = _try_metric(candidate, "brier_score", stat)
            if v is not None:
                j -= abs(weights.w_brier) * v
                terms["brier_score"] = v
        if weights.w_ece:
            v = _try_metric(candidate, "ece", stat)
            if v is not None:
                j -= abs(weights.w_ece) * v
                terms["ece"] = v
    except KeyError as e:
        return ObjectiveResult(
            value=weights.infeasible_value,
            feasible=False,
            reason=f"metric:{e!s}",
            details=details,
        )

    details["metric_terms"] = terms

    stab = root / "stability" / "stability_summary.json"
    n_dmp: Optional[int] = None
    n_genes: Optional[int] = None

    need_stability = (
        weights.w_stability_panel
        or weights.w_stable_genes
        or weights.min_stable_dmps is not None
        or weights.min_stable_genes is not None
    )
    if need_stability and not stab.is_file():
        if weights.min_stable_dmps is not None or weights.min_stable_genes is not None:
            if not weights.relax_min_stable:
                return ObjectiveResult(
                    value=weights.infeasible_value,
                    feasible=False,
                    reason="stability_summary_required",
                    details=details,
                )
    elif stab.is_file():
        with open(stab, encoding="utf-8") as f:
            st = json.load(f)
        dmp = st.get("dmp_stability")
        if isinstance(dmp, dict) and "stable_dmps_at_threshold" in dmp:
            n_dmp = int(dmp["stable_dmps_at_threshold"])
            details["n_stable_dmps"] = n_dmp
        gene = st.get("gene_stability")
        if isinstance(gene, dict) and "stable_genes_at_threshold" in gene:
            n_genes = int(gene["stable_genes_at_threshold"])
            details["n_stable_genes"] = n_genes
        if weights.w_stability_panel and n_dmp is not None:
            r = _panel_reward(float(n_dmp), weights.stability_panel_cap)
            j += weights.w_stability_panel * r
            details["stability_panel_reward"] = r
        if weights.w_stable_genes and n_genes is not None:
            r = _panel_reward(float(n_genes), weights.stability_gene_cap)
            j += weights.w_stable_genes * r
            details["stability_gene_reward"] = r
        if (
            weights.min_stable_dmps is not None
            and n_dmp is not None
            and n_dmp < weights.min_stable_dmps
        ):
            if not weights.relax_min_stable:
                return ObjectiveResult(
                    value=weights.infeasible_value,
                    feasible=False,
                    reason=f"min_stable_dmps",
                    details={**details, "got": n_dmp, "min": weights.min_stable_dmps},
                )
        if (
            weights.min_stable_genes is not None
            and n_genes is not None
            and n_genes < weights.min_stable_genes
        ):
            if not weights.relax_min_stable:
                return ObjectiveResult(
                    value=weights.infeasible_value,
                    feasible=False,
                    reason="min_stable_genes",
                    details=details,
                )

    if math.isnan(j):
        return ObjectiveResult(
            value=weights.infeasible_value, feasible=False, reason="nan_objective", details=details
        )
    return ObjectiveResult(value=j, feasible=True, reason="ok", details=details)
