"""
CLI: backfill full V2 sample QC JSON from an on-disk sample folder.

See scripts/methyl_sample_qc_backfill.py for usage examples.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from methyl_alignment_qc.core.writer import build_sample_qc_v2_dict, write_sample_qc_json
from methyl_alignment_qc.models.config import (
    AlignmentGuardrailsConfig,
    BisulfiteConversionConfig,
    CycleScreeningConfig,
    FragmentomicsConfig,
    OptionalGuardrailsConfig,
)
from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config
from methyl_utils.analyte_profiles import merge_step_config


def _load_step_config_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"Step config must be a JSON object: {path}")
    return data


def _kwargs_from_step_config(step_cfg: Dict[str, Any], *, validate_schema: bool) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"validate_schema": validate_schema}
    if step_cfg.get("fragmentomics") is not None:
        kwargs["fragmentomics"] = FragmentomicsConfig.model_validate(step_cfg["fragmentomics"])
    if step_cfg.get("bisulfite_conversion") is not None:
        kwargs["bisulfite_conversion"] = BisulfiteConversionConfig.model_validate(
            step_cfg["bisulfite_conversion"]
        )
    if step_cfg.get("cycle_screening") is not None:
        kwargs["cycle_screening"] = CycleScreeningConfig.model_validate(step_cfg["cycle_screening"])
    else:
        kwargs["cycle_screening"] = CycleScreeningConfig()
    if step_cfg.get("optional_guardrails") is not None:
        kwargs["optional_guardrails"] = OptionalGuardrailsConfig.model_validate(
            step_cfg["optional_guardrails"]
        )
    if step_cfg.get("alignment_guardrails") is not None:
        kwargs["alignment_guardrails"] = AlignmentGuardrailsConfig.model_validate(
            step_cfg["alignment_guardrails"]
        )
    return kwargs


def resolve_backfill_kwargs(
    *,
    project: Optional[Path],
    step_override: Optional[Path],
    step_config: Optional[Path],
    analyte: Optional[str],
    validate_schema: bool,
) -> Dict[str, Any]:
    """Build keyword arguments for build_sample_qc_v2_dict."""
    if project is not None:
        cfg = resolve_alignment_qc_config(project, step_override)
        return {
            "validate_schema": validate_schema,
            "fragmentomics": cfg.fragmentomics,
            "bisulfite_conversion": cfg.bisulfite_conversion,
            "cycle_screening": cfg.cycle_screening or CycleScreeningConfig(),
            "optional_guardrails": cfg.optional_guardrails,
            "alignment_guardrails": cfg.alignment_guardrails,
        }

    step_cfg: Dict[str, Any] = {}
    if step_config is not None:
        step_cfg = _load_step_config_json(step_config)
    if analyte:
        step_cfg = merge_step_config("alignment_qc", step_cfg, analyte)

    return _kwargs_from_step_config(step_cfg, validate_schema=validate_schema)


def _failed_guardrail_keys(guardrails: Dict[str, Any]) -> List[str]:
    details = guardrails.get("details") or {}
    if not isinstance(details, dict):
        return []
    failed: List[str] = []
    for key, metric in details.items():
        if key == "screening":
            continue
        if isinstance(metric, dict) and metric.get("pass") is False:
            failed.append(str(key))
    screening = details.get("screening")
    if isinstance(screening, dict) and screening.get("disposition") not in (None, "", "pass", "PASS"):
        failed.append("screening")
    return failed


def print_guardrail_summary(payload: Dict[str, Any], *, stream=None) -> None:
    stream = stream or sys.stderr
    guardrails = payload.get("guardrails") or {}
    sample_id = payload.get("sample_id", "?")
    overall = guardrails.get("overall_pass")
    recommendation = guardrails.get("recommendation", "")
    failed = _failed_guardrail_keys(guardrails)
    print(f"sample_id={sample_id} overall_pass={overall}", file=stream)
    if recommendation:
        print(f"  recommendation: {recommendation}", file=stream)
    if failed:
        print(f"  failed_guardrails: {', '.join(failed)}", file=stream)
    screening = (guardrails.get("details") or {}).get("screening")
    if isinstance(screening, dict) and screening.get("disposition"):
        print(f"  screening_disposition: {screening.get('disposition')}", file=stream)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build V2 sample QC JSON with full guardrails from a sample directory.",
    )
    parser.add_argument(
        "sample_dir",
        type=Path,
        help="Sample folder ({sample_id}/{sample_id}.json, *.deduplicate_metrics.txt, optional .bam)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output JSON path (default: {sample_dir}/{sample_id}.sample_qc.json)",
    )
    parser.add_argument("--stdout", action="store_true", help="Also write JSON to stdout")
    parser.add_argument(
        "--analyte",
        choices=["cfdna", "buffy_coat", "combined"],
        help="Apply analyte profile defaults for alignment_qc guardrails",
    )
    parser.add_argument("--project", "-p", type=Path, help="Pipeline project JSON (alignment_qc step_config)")
    parser.add_argument("--step-override", type=Path, help="JSON overrides merged with project alignment_qc")
    parser.add_argument(
        "--step-config",
        type=Path,
        metavar="JSON",
        help="Standalone alignment_qc step_config JSON (no project file)",
    )
    parser.add_argument("--no-validate", action="store_true", help="Skip schema validation")
    parser.add_argument(
        "--quiet-summary",
        action="store_true",
        help="Do not print guardrail pass/fail summary on stderr",
    )
    args = parser.parse_args(argv)

    sample_dir = args.sample_dir.resolve()
    if not sample_dir.is_dir():
        print(f"Sample directory not found: {sample_dir}", file=sys.stderr)
        return 1

    out_path = args.output or (sample_dir / f"{sample_dir.name}.sample_qc.json")

    try:
        kwargs = resolve_backfill_kwargs(
            project=args.project,
            step_override=args.step_override,
            step_config=args.step_config,
            analyte=args.analyte,
            validate_schema=not args.no_validate,
        )
        payload = build_sample_qc_v2_dict(
            sample_dir,
            output_path_for_history=out_path,
            **kwargs,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not args.stdout:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_sample_qc_json(payload, out_path)
        if not args.quiet_summary:
            print(f"Wrote {out_path}", file=sys.stderr)
    else:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")

    if not args.quiet_summary:
        print_guardrail_summary(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
