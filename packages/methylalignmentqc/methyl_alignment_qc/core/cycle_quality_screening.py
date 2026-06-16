"""Read-end-aware cycle quality screening for alignment QC remediation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..models.config import CycleScreeningConfig

DISPOSITION_USE_CURRENT = "USE_CURRENT_ALIGNMENT"
DISPOSITION_R2_TRIM = "REALIGN_READ2_TRIM"
DISPOSITION_MULTI_REGION = "INVESTIGATE_MULTI_REGION"
DISPOSITION_GUARDRAIL_ONLY = "INVESTIGATE_GUARDRAIL_ONLY"
DISPOSITION_NOT_FIXABLE = "NOT_FIXABLE"


@dataclass
class DipRegion:
    start_cycle: int
    end_cycle: int

    def to_dict(self) -> Dict[str, int]:
        return {"start_cycle": self.start_cycle, "end_cycle": self.end_cycle}


def _extract_cycle_qualities(payload: Dict[str, Any]) -> List[Tuple[int, float]]:
    mqc = payload.get("mean_quality_by_cycle") or {}
    if "rows" in mqc:
        rows = mqc.get("rows") or []
        return [(int(r["cycle"]), float(r["mean_quality"])) for r in rows]
    cycles = mqc.get("cycle") or []
    quals = mqc.get("mean_quality") or []
    return list(zip([int(c) for c in cycles], [float(q) for q in quals]))


def _find_dip_regions(
    cycle_quals: List[Tuple[int, float]],
    threshold: float,
    *,
    min_cycles: int = 1,
) -> List[DipRegion]:
    regions: List[DipRegion] = []
    run_start: Optional[int] = None
    run_len = 0
    prev_cycle: Optional[int] = None

    for cycle, qual in cycle_quals:
        if qual < threshold:
            if run_start is None:
                run_start = cycle
            run_len += 1
            prev_cycle = cycle
        elif run_start is not None and prev_cycle is not None:
            if run_len >= min_cycles:
                regions.append(DipRegion(run_start, prev_cycle))
            run_start = None
            run_len = 0
            prev_cycle = None

    if run_start is not None and prev_cycle is not None and run_len >= min_cycles:
        regions.append(DipRegion(run_start, prev_cycle))

    return regions


def _region_in_r2_start_window(region: DipRegion, r2_start: int, window: int) -> bool:
    window_end = r2_start + window - 1
    return region.start_cycle >= r2_start and region.end_cycle <= window_end


def _compute_trim_front2(
    cycle_quals: List[Tuple[int, float]],
    r2_start: int,
    threshold: float,
    recovery_cycles: int,
    max_trim: int,
) -> int:
    by_cycle = {c: q for c, q in cycle_quals}
    trim = 0
    for offset in range(max_trim):
        cycle = r2_start + offset
        if cycle not in by_cycle:
            break
        if by_cycle[cycle] < threshold:
            trim += 1
        else:
            break

    if trim == 0:
        return 0

    recovery_start = r2_start + trim
    recovered = False
    for offset in range(recovery_cycles):
        cycle = recovery_start + offset
        if cycle not in by_cycle:
            break
        if by_cycle[cycle] >= threshold:
            recovered = True
            break

    if not recovered and trim > 0:
        return min(trim, max_trim)
    return min(trim, max_trim) if trim > 0 else 0


def _cycles_acceptable(guardrails: Dict[str, Any], threshold: float) -> bool:
    details = guardrails.get("details") or {}
    for key in ("mean_quality", "min_quality_post20"):
        node = details.get(key)
        if isinstance(node, dict) and node.get("pass") is False:
            return False
    return True


def _failed_guardrail_keys(guardrails: Dict[str, Any]) -> List[str]:
    details = guardrails.get("details") or {}
    failed: List[str] = []
    for key, node in details.items():
        if key in ("fragmentomics", "bisulfite_conversion"):
            continue
        if isinstance(node, dict) and node.get("pass") is False:
            failed.append(str(key))
        elif isinstance(node, dict):
            for sub_key, sub_node in node.items():
                if isinstance(sub_node, dict) and sub_node.get("pass") is False:
                    failed.append(f"{key}.{sub_key}")
    return failed


def screen_cycle_quality(
    payload: Dict[str, Any],
    guardrails: Dict[str, Any],
    config: Optional[CycleScreeningConfig] = None,
) -> Dict[str, Any]:
    """Return screening report dict for guardrails.screening."""
    cfg = config or CycleScreeningConfig()
    cycle_quals = _extract_cycle_qualities(payload)
    if not cycle_quals:
        return {
            "disposition": DISPOSITION_NOT_FIXABLE,
            "read_length": 0,
            "r2_start_cycle": 0,
            "trim_front2": 0,
            "r2_start_mean_quality": None,
            "r2_recovery_mean_quality": None,
            "dip_regions": [],
            "message": "No mean_quality_by_cycle data available for screening.",
        }

    max_cycle = max(c for c, _ in cycle_quals)
    read_length = cfg.read_length or (max_cycle // 2)
    if max_cycle % 2 != 0 and cfg.read_length is None:
        read_length = max_cycle // 2
    r2_start = read_length + 1
    threshold = cfg.r2_quality_threshold
    window = cfg.r2_start_window_cycles

    overall_pass = bool(guardrails.get("overall_pass"))
    if overall_pass:
        return {
            "disposition": DISPOSITION_USE_CURRENT,
            "read_length": read_length,
            "r2_start_cycle": r2_start,
            "trim_front2": 0,
            "r2_start_mean_quality": None,
            "r2_recovery_mean_quality": None,
            "dip_regions": [],
            "message": "Alignment QC passed; no remediation required.",
        }

    dip_regions = _find_dip_regions(cycle_quals, threshold)
    dip_dicts = [r.to_dict() for r in dip_regions]

    r2_window_regions = [r for r in dip_regions if _region_in_r2_start_window(r, r2_start, window)]
    non_r2_regions = [r for r in dip_regions if not _region_in_r2_start_window(r, r2_start, window)]

    trim_front2 = _compute_trim_front2(
        cycle_quals,
        r2_start,
        threshold,
        cfg.recovery_cycles,
        cfg.max_trim_bases,
    )

    by_cycle = {c: q for c, q in cycle_quals}
    r2_quals = [by_cycle[c] for c in range(r2_start, r2_start + window) if c in by_cycle]
    r2_start_mean = sum(r2_quals) / len(r2_quals) if r2_quals else None
    recovery_quals = [
        by_cycle[c]
        for c in range(r2_start + trim_front2, r2_start + trim_front2 + cfg.recovery_cycles)
        if c in by_cycle
    ]
    r2_recovery_mean = sum(recovery_quals) / len(recovery_quals) if recovery_quals else None

    cycles_ok = _cycles_acceptable(guardrails, threshold)

    if len(dip_regions) >= cfg.multi_region_min_separate_dips and (
        len(non_r2_regions) > 0 or len(r2_window_regions) > 1
    ):
        disposition = DISPOSITION_MULTI_REGION
        message = (
            f"Multiple low-quality cycle regions detected ({len(dip_regions)}); "
            "manual FastQC / sliding-window review recommended."
        )
    elif r2_window_regions and trim_front2 >= 1 and not non_r2_regions:
        disposition = DISPOSITION_R2_TRIM
        end_cycle = r2_start + trim_front2 - 1
        message = (
            f"Read 2 start low quality (cycles {r2_start}–{end_cycle}); "
            f"recommended trim_front2={trim_front2} before realign."
        )
    elif cycles_ok:
        failed = _failed_guardrail_keys(guardrails)
        disposition = DISPOSITION_GUARDRAIL_ONLY
        message = (
            "Per-cycle quality acceptable but alignment guardrails failed "
            f"({', '.join(failed) or 'unknown'}); investigate duplication, insert size, or depth."
        )
    else:
        disposition = DISPOSITION_NOT_FIXABLE
        message = "Alignment QC failed without a fixable Read 2 start trim pattern."

    return {
        "disposition": disposition,
        "read_length": read_length,
        "r2_start_cycle": r2_start,
        "trim_front2": trim_front2 if disposition == DISPOSITION_R2_TRIM else 0,
        "r2_start_mean_quality": round(r2_start_mean, 3) if r2_start_mean is not None else None,
        "r2_recovery_mean_quality": round(r2_recovery_mean, 3) if r2_recovery_mean is not None else None,
        "dip_regions": dip_dicts,
        "message": message,
    }


def failed_guardrail_keys(guardrails: Dict[str, Any]) -> List[str]:
    """Public wrapper for failed guardrail key collection."""
    return _failed_guardrail_keys(guardrails)


def apply_screening_recommendations(guardrails: Dict[str, Any], screening: Dict[str, Any]) -> None:
    """Update recommendation/next_steps from screening disposition."""
    disposition = screening.get("disposition")
    trim = int(screening.get("trim_front2") or 0)
    if disposition == DISPOSITION_USE_CURRENT:
        return
    if disposition == DISPOSITION_R2_TRIM and trim > 0:
        guardrails["recommendation"] = (
            f"REMEDIATE: Trim {trim} bases from Read 2 start (fastp --trim_front2 {trim}) and realign."
        )
        guardrails["next_steps"] = (
            "Run sample.trim_fastq then parabricks with forceRealign; re-run methyl_qc before extract."
        )
    elif disposition == DISPOSITION_MULTI_REGION:
        guardrails["recommendation"] = "FAIL: Multiple low-quality regions; not fixable by R2 front-trim alone."
        guardrails["next_steps"] = (
            "Run FastQC per-base quality profile; consider sliding-window trim (SLIDINGWINDOW:4:20) or tail crop."
        )
    elif disposition == DISPOSITION_GUARDRAIL_ONLY:
        guardrails["recommendation"] = (
            "FAIL: Guardrail failure with acceptable cycle quality; investigate non-sequence metrics."
        )
        guardrails["next_steps"] = (
            "Review duplication rate, insert size distribution, and total read count; check library prep logs."
        )
