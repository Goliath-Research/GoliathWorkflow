"""
Convert legacy (V1 columnar) AlignmentQC sample JSON to V2 row-oriented JSON.

V1 payloads match ExportedSampleQCPayload; V2 payloads match ExportedSampleQCV2Payload.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from methyl_alignment_qc import __version__ as package_version
from methyl_alignment_qc.models.sample_qc import ExportedSampleQCPayload
from methyl_alignment_qc.models.sample_qc_v2 import (
    ArtifactSummariesRow,
    ArtifactSummariesV2,
    BaseDistributionByCycleRow,
    BaseDistributionByCycleV2,
    DuplicationHistogramRow,
    DuplicationHistogramV2,
    ErrorSummariesRow,
    ErrorSummariesV2,
    ExportedSampleQCV2Payload,
    GCBiasDetailsRow,
    GCBiasDetailsV2,
    InsertSizeHistogramRow,
    InsertSizeHistogramV2,
    MeanQualityByCycleRow,
    MeanQualityByCycleV2,
    QCV2Metadata,
    QCV2Producer,
    QualityScoreDistributionRow,
    QualityScoreDistributionV2,
)

from .guardrail_migration import migrate_guardrails_payload


def is_v2_alignment_qc_payload(payload: Dict[str, Any]) -> bool:
    """Return True if payload appears to be canonical V2 (row-oriented) export."""
    if not isinstance(payload, dict):
        return False
    md = payload.get("metadata")
    if not isinstance(md, dict):
        return False
    ver = str(md.get("schema_version", "")).strip()
    if ver.startswith("2."):
        return True
    name = str(md.get("schema_name", "")).strip()
    return name == "methylalignmentqc.sample_qc" and ver.startswith("2")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def v1_model_to_v2(
    v1: ExportedSampleQCPayload,
    *,
    exported_at_utc: str | None = None,
) -> ExportedSampleQCV2Payload:
    """Build V2 payload from a validated V1 model."""
    ts = exported_at_utc if exported_at_utc is not None else _utc_now_iso()
    metadata = QCV2Metadata(
        schema_name="methylalignmentqc.sample_qc",
        schema_version="2.0.0",
        exported_at_utc=ts,
        producer=QCV2Producer(package="methyl_alignment_qc", version=package_version),
    )

    mqc = v1.mean_quality_by_cycle
    mean_rows = [
        MeanQualityByCycleRow(cycle=int(c), mean_quality=float(mq)) for c, mq in zip(mqc.cycle, mqc.mean_quality)
    ]

    qsd = v1.quality_score_distribution
    q_rows = [
        QualityScoreDistributionRow(q=int(q), count_of_q=int(cq)) for q, cq in zip(qsd.Q, qsd.COUNT_OF_Q)
    ]

    bd = v1.base_distribution_by_cycle
    base_rows = [
        BaseDistributionByCycleRow(
            cycle=int(c),
            pct_a=float(a),
            pct_c=float(cc),
            pct_g=float(g),
            pct_t=float(t),
            pct_n=float(n),
        )
        for c, a, cc, g, t, n in zip(
            bd.cycle,
            bd.PCT_A,
            bd.PCT_C,
            bd.PCT_G,
            bd.PCT_T,
            bd.PCT_N,
        )
    ]

    gcd = v1.gc_bias_details
    gc_rows = [
        GCBiasDetailsRow(
            gc=int(gc),
            windows=int(w),
            read_starts=int(rs),
            mean_base_quality=float(mbq),
            normalized_coverage=float(nc),
            error_bar=float(eb),
        )
        for gc, w, rs, mbq, nc, eb in zip(
            gcd.GC,
            gcd.WINDOWS,
            gcd.READ_STARTS,
            gcd.MEAN_BASE_QUALITY,
            gcd.NORMALIZED_COVERAGE,
            gcd.ERROR_BAR,
        )
    ]

    ish = v1.insert_size_histogram
    insert_rows: List[InsertSizeHistogramRow] = []
    n_ins = len(ish.insert_size)
    for i in range(n_ins):
        insert_rows.append(
            InsertSizeHistogramRow(
                insert_size=int(ish.insert_size[i]),
                pair_orientation=str(ish.pair_orientation[i]),
                all_reads_fr_count=int(ish.all_reads_fr_count[i]),
                value=float(ish.VALUE[i]) if i < len(ish.VALUE) else None,
                all_sets=int(ish.all_sets[i]) if i < len(ish.all_sets) else None,
                optical_sets=int(ish.optical_sets[i]) if i < len(ish.optical_sets) else None,
                non_optical_sets=int(ish.non_optical_sets[i]) if i < len(ish.non_optical_sets) else None,
            )
        )

    es = v1.error_summaries
    err_rows = [
        ErrorSummariesRow(
            ref=str(rf),
            alt=str(alt),
            count=int(cnt),
            rate=float(rate),
            qscore=int(qs),
        )
        for rf, alt, cnt, rate, qs in zip(es.REF, es.ALT, es.COUNT, es.RATE, es.QSCORE)
    ]

    def _artifact_rows(art: Any) -> List[ArtifactSummariesRow]:
        return [
            ArtifactSummariesRow(
                artifact_name=str(nm),
                total_qscore=int(tq),
                worst_cxt=str(wx),
                worst_cxt_qscore=int(wxq),
            )
            for nm, tq, wx, wxq in zip(art.ARTIFACT_NAME, art.TOTAL_QSCORE, art.WORST_CXT, art.WORST_CXT_QSCORE)
        ]

    duph = v1.duplication_histogram
    dup_rows: List[DuplicationHistogramRow] = []
    for i in range(len(duph.BIN)):
        dup_rows.append(
            DuplicationHistogramRow(
                bin=float(duph.BIN[i]),
                value=float(duph.VALUE[i]),
                all_sets=int(duph.all_sets[i]) if i < len(duph.all_sets) else None,
                optical_sets=int(duph.optical_sets[i]) if i < len(duph.optical_sets) else None,
                non_optical_sets=int(duph.non_optical_sets[i]) if i < len(duph.non_optical_sets) else None,
            )
        )

    return ExportedSampleQCV2Payload(
        metadata=metadata,
        sample_id=v1.sample_id,
        quality_yield=v1.quality_yield,
        mean_quality_by_cycle=MeanQualityByCycleV2(rows=mean_rows),
        quality_score_distribution=QualityScoreDistributionV2(rows=q_rows),
        base_distribution_by_cycle=BaseDistributionByCycleV2(rows=base_rows),
        gc_bias_summary=v1.gc_bias_summary,
        gc_bias_details=GCBiasDetailsV2(rows=gc_rows),
        insert_size_metrics=v1.insert_size_metrics,
        insert_size_histogram=InsertSizeHistogramV2(rows=insert_rows),
        error_summaries=ErrorSummariesV2(rows=err_rows),
        pre_adapter_summaries=ArtifactSummariesV2(rows=_artifact_rows(v1.pre_adapter_summaries)),
        bait_bias_summaries=ArtifactSummariesV2(rows=_artifact_rows(v1.bait_bias_summaries)),
        conversion_log=v1.conversion_log,
        duplication_metrics=list(v1.duplication_metrics),
        duplication_histogram=DuplicationHistogramV2(rows=dup_rows),
        summary_stats=v1.summary_stats,
        guardrails=v1.guardrails,
    )


def v1_dict_to_v2_model(raw: Dict[str, Any]) -> ExportedSampleQCV2Payload:
    """Migrate guardrails if needed, validate as V1, then convert to V2."""
    migrated, _ = migrate_guardrails_payload(raw)
    v1 = ExportedSampleQCPayload.model_validate(migrated)
    return v1_model_to_v2(v1)


def v1_dict_to_v2_dict(raw: Dict[str, Any], *, exported_at_utc: str | None = None) -> Dict[str, Any]:
    v2 = v1_dict_to_v2_model(raw)
    if exported_at_utc is not None:
        v2 = v2.model_copy(
            update={
                "metadata": v2.metadata.model_copy(
                    update={"exported_at_utc": exported_at_utc},
                )
            }
        )
    return v2.model_dump(mode="python", by_alias=True, exclude_none=True)


def _iter_json_files(target: Path, recursive: bool = True) -> Iterable[Path]:
    if target.is_file() and target.suffix.lower() == ".json":
        yield target
        return

    if target.is_dir():
        pattern = "**/*.json" if recursive else "*.json"
        for path in sorted(target.glob(pattern)):
            if path.is_file():
                yield path


def _default_output_path_for_input(path: Path) -> Path:
    return path.with_name(path.stem + ".v2.json")


def convert_file(
    path: Path,
    *,
    apply: bool = False,
    backup: bool = False,
    output_path: Path | None = None,
    validate_v2: bool = True,
) -> Tuple[bool, str]:
    """
    Convert one JSON file from V1 to V2.

    Returns (changed_or_success, status_message).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        return False, f"ERROR reading {path}: {e}"

    if is_v2_alignment_qc_payload(payload):
        return False, f"SKIP {path} (already V2)"

    try:
        v2_dict = v1_dict_to_v2_dict(payload)
    except Exception as e:
        return False, f"ERROR converting {path}: {e}"

    if validate_v2:
        try:
            ExportedSampleQCV2Payload.model_validate(v2_dict)
        except Exception as e:
            return False, f"ERROR V2 validation {path}: {e}"

    if not apply:
        return True, f"WOULD CONVERT {path}"

    out = output_path if output_path is not None else _default_output_path_for_input(path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        if backup and out.exists():
            bak = out.with_suffix(out.suffix + ".bak")
            bak.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(v2_dict, f, indent=2)
    except Exception as e:
        return False, f"ERROR writing {out}: {e}"

    return True, f"CONVERTED {path} -> {out}"


def convert_directory(
    source_dir: Path,
    output_dir: Path,
    *,
    recursive: bool = True,
    apply: bool = False,
    validate_v2: bool = True,
) -> List[Tuple[bool, str]]:
    """Convert all V1 JSON files under source_dir into output_dir (flat mirror by basename)."""
    results: List[Tuple[bool, str]] = []
    for src in _iter_json_files(source_dir, recursive=recursive):
        if not apply:
            try:
                with open(src, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception as e:
                results.append((False, f"ERROR reading {src}: {e}"))
                continue
            if is_v2_alignment_qc_payload(payload):
                results.append((False, f"SKIP {src} (already V2)"))
                continue
            try:
                v1_dict_to_v2_dict(payload)
            except Exception as e:
                results.append((False, f"ERROR converting {src}: {e}"))
                continue
            results.append((True, f"WOULD CONVERT {src} -> {output_dir / (src.stem + '.v2.json')}"))
            continue

        out = output_dir / (src.stem + ".v2.json")
        ok, msg = convert_file(src, apply=True, backup=False, output_path=out, validate_v2=validate_v2)
        results.append((ok, msg))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert AlignmentQC V1 (columnar) JSON files to V2 (row-oriented).",
    )
    parser.add_argument("target", type=Path, help="Path to a JSON file or directory of JSON files")
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="When target is a directory, only scan top-level *.json files",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write V2 JSON files. Default is dry-run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="When target is a single file and --apply is set, write to this path (default: <stem>.v2.json next to input)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="When target is a directory and --apply is set, required: directory for converted *.v2.json files",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="When used with --apply and --output, if the output file exists write a .bak copy first",
    )
    parser.add_argument(
        "--no-validate-v2",
        action="store_true",
        help="Skip validating converted payload against ExportedSampleQCV2Payload",
    )
    args = parser.parse_args()

    target = args.target
    if not target.exists():
        print(f"Error: target does not exist: {target}")
        raise SystemExit(1)

    validate_v2 = not args.no_validate_v2

    if target.is_file():
        if args.output_dir is not None:
            print("Warning: --output-dir is ignored when target is a single file")

        ok, msg = convert_file(
            target,
            apply=args.apply,
            backup=args.backup,
            output_path=args.output,
            validate_v2=validate_v2,
        )
        print(msg)
        raise SystemExit(0 if ok or msg.startswith("SKIP") else 1)

    # Directory
    if args.apply and args.output_dir is None:
        print("Error: --output-dir is required when converting a directory with --apply")
        raise SystemExit(1)

    if not args.apply:
        files = list(_iter_json_files(target, recursive=not args.no_recursive))
        if not files:
            print(f"No JSON files found under: {target}")
            raise SystemExit(1)
        converted = 0
        for src in files:
            try:
                with open(src, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception as e:
                print(f"ERROR reading {src}: {e}")
                continue
            if is_v2_alignment_qc_payload(payload):
                print(f"SKIP {src} (already V2)")
                continue
            try:
                v1_dict_to_v2_dict(payload)
            except Exception as e:
                print(f"ERROR converting {src}: {e}")
                continue
            print(f"WOULD CONVERT {src}")
            converted += 1
        print(f"\nScanned {len(files)} file(s); {converted} file(s) would be converted (dry-run).")
        raise SystemExit(0)

    out_dir = args.output_dir
    assert out_dir is not None
    results = convert_directory(
        target,
        out_dir,
        recursive=not args.no_recursive,
        apply=True,
        validate_v2=validate_v2,
    )
    ok_count = sum(1 for ok, m in results if ok and m.startswith("CONVERTED"))
    for ok, m in results:
        print(m)
    print(f"\nDone. {ok_count} file(s) written under {out_dir}.")


if __name__ == "__main__":
    main()
