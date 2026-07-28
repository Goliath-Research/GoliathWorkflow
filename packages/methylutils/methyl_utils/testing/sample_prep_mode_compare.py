"""Linear vs ``pangenome_wgbs`` SamplePrep experiment helpers (no DB).

Layout contract (lab / QNAP shape):

```text
/work/samples/<sampleId>/
  <sampleId>_1.fastq.gz          # shared root FASTQs
  <sampleId>_2.fastq.gz
  linear/                        # experiment-only mode tree
  pangenome_wgbs/                # experiment-only mode tree
```

Mode subdirs are temporary scaffolding for dual-align comparison, not a new
production / lab / QNAP convention.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..test_data_registry import SamplePrepCanaryThresholds
from .sample_prep_canary import (
    MODE_ALIGN_ACTION,
    CheckResult,
    ModeReport,
    compare_linear_vs_wgbs,
    compute_cg_overlap_stats,
    mode_report_to_dict,
    validate_mode_artifacts,
)

COMPARE_MODES: Tuple[str, ...] = ("linear", "pangenome_wgbs")

_ALIGN_ACTION_NAMES = {
    "linear": {
        "sample.parabricks_fq2bam",
        "sample.parabricks_fq2bam_meth",
        "parabricks_fq2bam",
    },
    "pangenome_wgbs": {
        "sample.methylgrapher_wgbs_align",
        "methylgrapher_wgbs_align",
    },
}


def sample_root_dir(samples_base: Path | str, sample_id: str) -> Path:
    return Path(samples_base).expanduser().resolve() / sample_id


def mode_sample_dir(sample_root: Path | str, mode: str) -> Path:
    if mode not in COMPARE_MODES:
        raise ValueError(f"unsupported compare mode: {mode}")
    return Path(sample_root).expanduser().resolve() / mode


def discover_root_fastqs(sample_root: Path | str, sample_id: str) -> List[Path]:
    """Return non-empty FASTQ files directly under the sample root (no /fastq child)."""
    root = Path(sample_root).expanduser().resolve()
    patterns = (
        f"{sample_id}_1.fastq.gz",
        f"{sample_id}_2.fastq.gz",
        f"{sample_id}_R1.fastq.gz",
        f"{sample_id}_R2.fastq.gz",
        f"{sample_id}.R1.fastq.gz",
        f"{sample_id}.R2.fastq.gz",
    )
    found: List[Path] = []
    for name in patterns:
        path = root / name
        if path.is_file() and path.stat().st_size > 0:
            found.append(path)
    if found:
        return sorted(set(found))
    # Fall back to any paired-looking FASTQs at root (not in mode subdirs).
    for path in sorted(root.glob("*.fastq.gz")) + sorted(root.glob("*.fq.gz")):
        if path.is_file() and path.stat().st_size > 0 and path.parent == root:
            found.append(path)
    return found


def ensure_mode_dir(sample_root: Path | str, mode: str) -> Path:
    mode_dir = mode_sample_dir(sample_root, mode)
    mode_dir.mkdir(parents=True, exist_ok=True)
    return mode_dir


def link_root_fastqs_into_mode(
    sample_root: Path | str,
    mode: str,
    *,
    sample_id: str,
    method: str = "hardlink",
) -> List[Path]:
    """Hardlink (or symlink/copy) root FASTQs into the mode sampleDir."""
    root = Path(sample_root).expanduser().resolve()
    mode_dir = ensure_mode_dir(root, mode)
    fastqs = discover_root_fastqs(root, sample_id)
    if not fastqs:
        raise FileNotFoundError(
            f"No non-empty root FASTQs under {root} for sample_id={sample_id}; "
            "download once to the sample root (lab/QNAP layout) or pass --reuse-local-fastq "
            "only when files already exist"
        )
    linked: List[Path] = []
    for src in fastqs:
        dest = mode_dir / src.name
        if dest.exists() or dest.is_symlink():
            if dest.is_file() and dest.stat().st_size > 0:
                linked.append(dest)
                continue
            dest.unlink(missing_ok=True)
        if method == "symlink":
            os.symlink(src, dest)
        elif method == "copy":
            import shutil

            shutil.copy2(src, dest)
        else:
            try:
                os.link(src, dest)
            except OSError:
                os.symlink(src, dest)
        linked.append(dest)
    return linked


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            yield row


def _action_name(row: Mapping[str, Any]) -> str:
    for key in ("action", "action_name", "actionName", "capability", "name"):
        val = row.get(key)
        if val:
            return str(val)
    return ""


def _duration_from_row(row: Mapping[str, Any]) -> Optional[float]:
    for key in ("duration_ms", "durationMs", "wall_ms"):
        val = row.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    outputs = row.get("outputs")
    if isinstance(outputs, dict):
        for key in ("duration_ms", "durationMs"):
            val = outputs.get(key)
            if val is None:
                continue
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    started = row.get("started_at_utc") or row.get("started_at")
    finished = row.get("finished_at_utc") or row.get("finished_at") or row.get("ts_utc")
    if started and finished:
        try:
            def _parse(ts: str) -> datetime:
                text = str(ts).replace("Z", "+00:00")
                return datetime.fromisoformat(text)

            delta = _parse(str(finished)) - _parse(str(started))
            ms = delta.total_seconds() * 1000.0
            if ms >= 0:
                return ms
        except (TypeError, ValueError):
            return None
    return None


def extract_alignment_duration_ms(
    sample_dir: Path | str,
    *,
    sample_id: str,
    mode: str,
    task_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Optional[float]:
    """Best-effort alignment wall time from task outputs, action log, or prep log."""
    sample_dir = Path(sample_dir)
    wanted = _ALIGN_ACTION_NAMES.get(mode) or {MODE_ALIGN_ACTION.get(mode, "")}
    wanted = {w for w in wanted if w}

    candidates: List[float] = []

    def _consider(rows: Iterable[Mapping[str, Any]]) -> None:
        for row in rows:
            name = _action_name(row)
            if name not in wanted and not any(w in name for w in wanted):
                continue
            dur = _duration_from_row(row)
            if dur is not None:
                candidates.append(dur)

    if task_rows:
        _consider(task_rows)

    for log_name in (
        "action_run_log.jsonl",
        f"{sample_id}.sample_prep_log.jsonl",
        f"{sample_dir.name}.sample_prep_log.jsonl",
    ):
        _consider(_iter_jsonl(sample_dir / log_name))

    if not candidates:
        return None
    # Prefer the maximum observed align duration (covers retries).
    return max(candidates)


def optional_h5_coverage_stats(
    sample_dir: Path | str,
    *,
    depth_thresholds: Optional[Sequence[int]] = None,
    max_files: int = 8,
    max_sites_per_file: int = 2_000_000,
) -> Dict[str, Any]:
    """Top-level H5 CpG coverage summary (no full dump).

    Uses ``mC + uC`` as per-site coverage when the MethylExtractor structured
    dataset is present. Returns empty dict when h5py/files are unavailable.
    """
    sample_dir = Path(sample_dir)
    h5_files = sorted(p for p in sample_dir.glob("*-CG.h5") if p.is_file())[:max_files]
    if not h5_files:
        return {}
    try:
        import h5py  # type: ignore
        import numpy as np
    except ImportError:
        return {"h5_stats_error": "h5py_or_numpy_unavailable", "n_h5_files_seen": len(h5_files)}

    coverages: List[Any] = []
    files_read = 0
    for path in h5_files:
        try:
            with h5py.File(path, "r") as handle:
                if "methylation_data" not in handle:
                    continue
                ds = handle["methylation_data"]
                n = int(ds.shape[0]) if getattr(ds, "shape", None) else 0
                if n <= 0:
                    continue
                take = min(n, max_sites_per_file)
                chunk = ds[:take]
                if "mC" in chunk.dtype.names and "uC" in chunk.dtype.names:
                    cov = np.asarray(chunk["mC"], dtype=np.float64) + np.asarray(
                        chunk["uC"], dtype=np.float64
                    )
                    coverages.append(cov)
                    files_read += 1
        except OSError:
            continue
    if not coverages:
        return {"n_h5_files_seen": len(h5_files), "n_h5_files_read": 0}

    import numpy as np

    all_cov = np.concatenate(coverages)
    out: Dict[str, Any] = {
        "n_h5_files_seen": len(h5_files),
        "n_h5_files_read": files_read,
        "n_sites_sampled": int(all_cov.size),
        "mean_coverage": float(np.mean(all_cov)) if all_cov.size else None,
        "median_coverage": float(np.median(all_cov)) if all_cov.size else None,
    }
    if depth_thresholds:
        fracs: Dict[str, float] = {}
        for depth in depth_thresholds:
            try:
                d = int(depth)
            except (TypeError, ValueError):
                continue
            if d < 0 or all_cov.size == 0:
                continue
            fracs[str(d)] = float(np.mean(all_cov >= d))
        out["fraction_cpgs_ge_depth"] = fracs
    return out


def enrich_mode_report_timing_and_h5(
    report: ModeReport,
    *,
    thresholds: Optional[SamplePrepCanaryThresholds] = None,
    task_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> ModeReport:
    """Attach alignment duration + optional H5 coverage stats onto a ModeReport."""
    thr = thresholds or SamplePrepCanaryThresholds()
    dur = extract_alignment_duration_ms(
        report.sample_dir,
        sample_id=report.sample_id,
        mode=report.mode,
        task_rows=task_rows,
    )
    if dur is not None:
        report.metrics["alignment_duration_ms"] = dur
    h5_stats = optional_h5_coverage_stats(
        report.sample_dir,
        depth_thresholds=thr.cpg_depth_thresholds,
    )
    if h5_stats:
        report.metrics["h5_coverage"] = h5_stats
    # After successful SamplePrep, delete_bam may remove BAM; keep extract QC as the gate.
    if report.metrics.get("extraction_qc_pass") is True or report.metrics.get("n_h5_files"):
        for check in report.checks:
            if check.name == "bam_present" and not check.ok:
                check.ok = True
                check.detail = f"{check.detail}; tolerated after delete_bam cleanup"
                break
    return report


def build_sample_compare_block(
    *,
    sample_id: str,
    linear: ModeReport,
    wgbs: ModeReport,
    thresholds: Optional[SamplePrepCanaryThresholds] = None,
) -> Dict[str, Any]:
    thr = thresholds or SamplePrepCanaryThresholds()
    checks = compare_linear_vs_wgbs(linear, wgbs, thresholds=thr)
    cov_l = linear.metrics.get("cpg_weighted_mean_coverage")
    cov_w = wgbs.metrics.get("cpg_weighted_mean_coverage")
    sites_l = linear.metrics.get("cpg_sites")
    sites_w = wgbs.metrics.get("cpg_sites")
    time_l = linear.metrics.get("alignment_duration_ms")
    time_w = wgbs.metrics.get("alignment_duration_ms")
    hypothesis = {
        "claim": (
            "pangenome_wgbs improves usable read support at CpG positions "
            "(coverage / site yield) vs linear; alignment runtime is a cost metric"
        ),
        "not_a_claim": "stock Giraffe methylation biology parity",
        "cpg_coverage_delta": None,
        "cpg_sites_delta": None,
        "alignment_time_ratio_wgbs_over_linear": None,
    }
    try:
        if cov_l is not None and cov_w is not None:
            hypothesis["cpg_coverage_delta"] = float(cov_w) - float(cov_l)
    except (TypeError, ValueError):
        pass
    try:
        if sites_l is not None and sites_w is not None:
            hypothesis["cpg_sites_delta"] = float(sites_w) - float(sites_l)
    except (TypeError, ValueError):
        pass
    try:
        if time_l and time_w and float(time_l) > 0:
            hypothesis["alignment_time_ratio_wgbs_over_linear"] = float(time_w) / float(time_l)
    except (TypeError, ValueError):
        pass

    return {
        "sample_id": sample_id,
        "ok": all(c.ok for c in linear.checks)
        and all(c.ok for c in wgbs.checks)
        and all(c.ok for c in checks),
        "linear": mode_report_to_dict(linear),
        "pangenome_wgbs": mode_report_to_dict(wgbs),
        "comparison_checks": [
            {"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks
        ],
        "hypothesis": hypothesis,
    }


def build_mode_compare_report(
    *,
    sample_blocks: Sequence[Mapping[str, Any]],
    thresholds: Optional[SamplePrepCanaryThresholds] = None,
    meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    overall = all(bool(b.get("ok")) for b in sample_blocks) if sample_blocks else False
    return {
        "schema_version": "1.0",
        "report_type": "sample_prep_linear_vs_pangenome_wgbs",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_pass": overall,
        "layout_policy": {
            "fastq_location": "sample_root",
            "mode_subdirs": list(COMPARE_MODES),
            "mode_subdirs_are": "experiment_only_scaffolding",
            "archive": "disabled_until_after_review",
        },
        "hypothesis": (
            "pangenome_wgbs improves usable read support at CpG positions "
            "(coverage/site yield); alignment wall time is reported as cost"
        ),
        "thresholds": thresholds.model_dump(mode="python") if thresholds else None,
        "samples": list(sample_blocks),
        "meta": dict(meta or {}),
    }


def write_mode_compare_markdown(report: Mapping[str, Any], path: Path) -> None:
    lines = [
        "# Linear vs pangenome_wgbs SamplePrep comparison",
        "",
        f"- Generated: `{report.get('generated_at_utc')}`",
        f"- Overall pass: **{report.get('overall_pass')}**",
        f"- Hypothesis: {report.get('hypothesis')}",
        "",
        "## Layout policy",
        "",
        "- FASTQs stay at `/work/samples/<sampleId>/` (lab/QNAP shape; no `/fastq` child).",
        "- `linear/` and `pangenome_wgbs/` are **experiment-only** trees so both arms can coexist.",
        "- `sampleStorage` omitted — no QNAP archive until after review.",
        "- After choosing a winner, promote that arm back to the flat sample tree and archive once.",
        "",
    ]
    for sample in report.get("samples") or []:
        sid = sample.get("sample_id")
        lines.append(f"## Sample `{sid}`")
        lines.append("")
        lines.append(f"- ok: `{sample.get('ok')}`")
        hyp = sample.get("hypothesis") or {}
        lines.append(
            f"- CpG coverage Δ (wgbs − linear): `{hyp.get('cpg_coverage_delta')}`"
        )
        lines.append(f"- CpG sites Δ (wgbs − linear): `{hyp.get('cpg_sites_delta')}`")
        lines.append(
            f"- Alignment time ratio (wgbs/linear): "
            f"`{hyp.get('alignment_time_ratio_wgbs_over_linear')}`"
        )
        lines.append("")
        for arm in ("linear", "pangenome_wgbs"):
            mode = sample.get(arm) or {}
            lines.append(f"### {arm}")
            lines.append("")
            lines.append(f"- sample_dir: `{mode.get('sample_dir')}`")
            metrics = mode.get("metrics") or {}
            focus = {
                k: metrics.get(k)
                for k in (
                    "mapping_rate",
                    "duplication_rate",
                    "cpg_weighted_mean_coverage",
                    "cpg_sites",
                    "alignment_duration_ms",
                    "extraction_qc_pass",
                    "h5_coverage",
                )
                if k in metrics
            }
            if focus:
                lines.append(f"- metrics: `{json.dumps(focus, sort_keys=True, default=str)}`")
            lines.append("")
        if sample.get("comparison_checks"):
            lines.append("| Check | OK | Detail |")
            lines.append("|-------|----|--------|")
            for check in sample.get("comparison_checks") or []:
                lines.append(
                    f"| {check.get('name')} | {check.get('ok')} | {check.get('detail')} |"
                )
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_compare_arm(
    *,
    mode: str,
    sample_id: str,
    sample_dir: Path,
    thresholds: Optional[SamplePrepCanaryThresholds] = None,
    observed_actions: Optional[Sequence[str]] = None,
    task_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> ModeReport:
    report = validate_mode_artifacts(
        mode=mode,
        sample_id=sample_id,
        sample_dir=sample_dir,
        thresholds=thresholds,
        observed_actions=observed_actions,
    )
    return enrich_mode_report_timing_and_h5(
        report, thresholds=thresholds, task_rows=task_rows
    )


def build_start_payload(
    *,
    sample_id: str,
    mode: str,
    sample_dir: Path,
    project_path: Path | str,
    workflow_version_id: Optional[int],
    primary_analyte: str,
    reference_fasta: str,
    fastq_storage: Mapping[str, Any],
    fastq_prefix: str = "",
    reference_gtf: Optional[str] = None,
    library_protocol: Optional[str] = None,
    pipeline_procedure: Optional[str] = None,
    action_config: Optional[Mapping[str, Any]] = None,
    program_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a sample-prep-start body for one experiment arm (no sampleStorage)."""
    body: Dict[str, Any] = {
        "projectPath": str(project_path),
        "alignmentMode": mode,
        "primaryAnalyte": primary_analyte,
        "referenceFasta": reference_fasta,
        "deleteFastqs": False,
        # Keep mode trees local: do not fill portal sampleStorage / QNAP archive.
        "disableArchive": True,
        "fastqStorage": dict(fastq_storage),
        "samples": [
            {
                "sampleId": sample_id,
                "sampleDir": str(sample_dir),
                # Explicit "." keeps file sources rooted at sampleDir (lab FASTQs are
                # hardlinked there). Empty string is treated as unset and becomes sampleId/.
                "fastqPrefix": fastq_prefix if fastq_prefix else ".",
            }
        ],
    }
    if reference_gtf:
        body["referenceGtf"] = str(reference_gtf)
    if program_path:
        # Prefer compiling the current DomainProgram when DB SamplePrep is stale.
        body["program_path"] = str(program_path)
    elif workflow_version_id is not None:
        body["workflow_version_id"] = int(workflow_version_id)
    if library_protocol:
        body["libraryProtocol"] = library_protocol
    if pipeline_procedure:
        body["pipelineProcedure"] = pipeline_procedure
    if action_config:
        body["actionConfig"] = dict(action_config)
    # Intentionally omit sampleStorage / sampleDestination (no QNAP archive).
    return body
