"""Pass/Fail guardrails for MethylExtractor extraction manifests."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .manifest import contexts_extracted
from .models.config import ExtractionQCGuardrailConfig

AUTOSOMAL_CHROMOSOMES = {str(i) for i in range(1, 23)}


def _metric(
    *,
    value: Any,
    normal_range: str,
    passed: bool,
    message: str,
) -> Dict[str, Any]:
    return {
        "value": value,
        "normal_range": normal_range,
        "pass": passed,
        "message": message,
    }


def _cg_mean_coverage(chrom_entry: Dict[str, Any]) -> Optional[float]:
    cg = chrom_entry.get("CG")
    if not isinstance(cg, dict):
        return None
    value = cg.get("mean_coverage")
    if value is None:
        return None
    return float(value)


def evaluate_guardrails(
    manifest: Dict[str, Any],
    *,
    config: ExtractionQCGuardrailConfig,
    expected_chromosomes: Iterable[str],
) -> Dict[str, Any]:
    summary = manifest.get("summary") or {}
    per_chromosome = manifest.get("per_chromosome") or {}
    extracted_contexts = set(contexts_extracted(manifest))
    expected = [str(chrom) for chrom in expected_chromosomes]

    results: Dict[str, Any] = {}

    cpg_cov = summary.get("cpg_weighted_mean_coverage")
    if cpg_cov is None:
        results["cpg_weighted_mean_coverage"] = _metric(
            value=None,
            normal_range=f">= {config.min_cpg_weighted_mean_coverage}",
            passed=False,
            message="Missing summary.cpg_weighted_mean_coverage in extraction manifest.",
        )
    else:
        cpg_cov_f = float(cpg_cov)
        passed = cpg_cov_f >= config.min_cpg_weighted_mean_coverage
        results["cpg_weighted_mean_coverage"] = _metric(
            value=round(cpg_cov_f, 4),
            normal_range=f">= {config.min_cpg_weighted_mean_coverage}",
            passed=passed,
            message=(
                "Genome-wide CpG weighted mean coverage on sites passing min_cov. "
                "Low values indicate insufficient read depth for methylation calling."
            ),
        )

    if "CHH" in extracted_contexts:
        chh = summary.get("chh_methylation_level")
        if chh is None:
            results["chh_methylation_level"] = _metric(
                value=None,
                normal_range=f"<= {config.max_chh_methylation_level}",
                passed=False,
                message="CHH context was extracted but summary.chh_methylation_level is missing.",
            )
        else:
            chh_f = float(chh)
            passed = chh_f <= config.max_chh_methylation_level
            results["chh_methylation_level"] = _metric(
                value=round(chh_f, 6),
                normal_range=f"<= {config.max_chh_methylation_level}",
                passed=passed,
                message=(
                    "Non-CpG CHH methylation should stay low in bisulfite-converted WGBS. "
                    "Elevated CHH suggests incomplete conversion or contamination."
                ),
            )

    if "CHG" in extracted_contexts:
        chg = summary.get("chg_methylation_level")
        if chg is None:
            results["chg_methylation_level"] = _metric(
                value=None,
                normal_range=f"<= {config.max_chg_methylation_level}",
                passed=False,
                message="CHG context was extracted but summary.chg_methylation_level is missing.",
            )
        else:
            chg_f = float(chg)
            passed = chg_f <= config.max_chg_methylation_level
            results["chg_methylation_level"] = _metric(
                value=round(chg_f, 6),
                normal_range=f"<= {config.max_chg_methylation_level}",
                passed=passed,
                message=(
                    "Non-CpG CHG methylation should stay low in bisulfite-converted WGBS. "
                    "Elevated CHG suggests incomplete conversion or contamination."
                ),
            )

    missing: List[str] = []
    for chrom in expected:
        chrom_entry = per_chromosome.get(chrom)
        if not isinstance(chrom_entry, dict) or not isinstance(chrom_entry.get("CG"), dict):
            missing.append(chrom)
    completeness_pass = not missing
    results["chromosome_completeness"] = _metric(
        value={
            "expected": expected,
            "missing": missing,
            "present_count": len(expected) - len(missing),
        },
        normal_range="all expected chromosomes present with CG metrics",
        passed=completeness_pass,
        message=(
            "Each expected chromosome must appear in manifest.per_chromosome with a CG block."
        ),
    )

    autosomal_coverages: List[float] = []
    for chrom in expected:
        if chrom not in AUTOSOMAL_CHROMOSOMES:
            continue
        chrom_entry = per_chromosome.get(chrom)
        if not isinstance(chrom_entry, dict):
            continue
        mean_cov = _cg_mean_coverage(chrom_entry)
        if mean_cov is not None:
            autosomal_coverages.append(mean_cov)

    if len(autosomal_coverages) < 2:
        uniformity_ratio = None
        uniformity_pass = True
        uniformity_message = (
            "Skipped autosomal uniformity check because fewer than two autosomal "
            "chromosomes were evaluated."
        )
    else:
        autosomal_coverages.sort()
        median = autosomal_coverages[len(autosomal_coverages) // 2]
        minimum = autosomal_coverages[0]
        uniformity_ratio = minimum / median if median > 0 else 0.0
        uniformity_pass = uniformity_ratio >= config.min_autosomal_coverage_uniformity_ratio
        uniformity_message = (
            "Autosomal CpG mean coverage should be uniform across chromosomes. "
            "Low min/median ratio flags localized dropout or mapping bias."
        )

    results["chromosome_uniformity"] = _metric(
        value={
            "min_autosomal_mean_coverage": round(min(autosomal_coverages), 4)
            if autosomal_coverages
            else None,
            "median_autosomal_mean_coverage": round(
                autosomal_coverages[len(autosomal_coverages) // 2], 4
            )
            if len(autosomal_coverages) >= 2
            else None,
            "min_over_median": round(uniformity_ratio, 4) if uniformity_ratio is not None else None,
        },
        normal_range=f">= {config.min_autosomal_coverage_uniformity_ratio}",
        passed=uniformity_pass,
        message=uniformity_message,
    )

    overall_pass = all(bool(item.get("pass")) for item in results.values())
    return {
        "metrics": results,
        "overall_pass": overall_pass,
    }
