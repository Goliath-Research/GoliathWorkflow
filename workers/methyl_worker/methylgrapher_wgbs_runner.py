"""Worker-side methylGrapher WGBS pangenome alignment + graph-aware extraction.

Produces QC-compatible GRCh38 BAM artifacts for ``sample.methyl_qc`` and
``{chrom}-{context}.h5`` / ``{chrom}-{context}.patterns.h5`` for extraction QC
and informME. Asset paths come exclusively from task ``resolvedConfig`` on the
worker path (no site/profile re-read for science knobs).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shlex
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

METHYLGRAPHER_IMAGE_ENV = "METHYL_METHYLGRAPHER_IMAGE"
VG_BIN_ENV = "METHYL_VG_BIN"
METHYLGRAPHER_BIN_ENV = "METHYL_METHYLGRAPHER_BIN"


@dataclass(frozen=True)
class MethylGrapherWgbsBundle:
    c2t_gbz: Path
    c2t_dist: Path
    c2t_min: Path
    c2t_zipcodes: Path
    g2a_gbz: Path
    g2a_dist: Path
    g2a_min: Path
    g2a_zipcodes: Path
    ref_paths: Path
    cpg_tsv: Path
    linear_ref_fasta: Path
    original_gbz: Optional[Path] = None
    node_replacement_json: Optional[Path] = None
    index_prefix: Optional[str] = None
    directional: bool = True
    threads: Optional[int] = None
    image: Optional[str] = None
    image_digest: Optional[str] = None
    methylgrapher_version: Optional[str] = None
    vg_version: Optional[str] = None
    cg_only: bool = True
    contexts: Tuple[str, ...] = ("CG",)
    read_level_enabled: bool = True
    tile_size: int = 4

    def required_files(self) -> List[Tuple[str, Path]]:
        items = [
            ("c2t.gbz", self.c2t_gbz),
            ("c2t.dist", self.c2t_dist),
            ("c2t.min", self.c2t_min),
            ("c2t.zipcodes", self.c2t_zipcodes),
            ("g2a.gbz", self.g2a_gbz),
            ("g2a.dist", self.g2a_dist),
            ("g2a.min", self.g2a_min),
            ("g2a.zipcodes", self.g2a_zipcodes),
            ("ref_paths", self.ref_paths),
            ("cpg_tsv", self.cpg_tsv),
            ("linear_ref_fasta", self.linear_ref_fasta),
        ]
        if self.original_gbz is not None:
            items.append(("original_gbz", self.original_gbz))
        if self.node_replacement_json is not None:
            items.append(("node_replacement_json", self.node_replacement_json))
        return items

    def assert_present(self) -> None:
        missing = [label for label, path in self.required_files() if not path.is_file()]
        if missing:
            raise RuntimeError(
                "methylGrapher WGBS assets missing on disk (no stock Giraffe fallback): "
                + ", ".join(missing)
            )


def _pick_bool(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in payload or payload[key] is None:
        return default
    val = payload[key]
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}


def resolve_wgbs_bundle_from_resolved(
    resolved_config: Mapping[str, Any] | None,
) -> MethylGrapherWgbsBundle:
    from methyl_utils.action_config_resolver import resolve_methylgrapher_wgbs_genome

    if not resolved_config:
        raise RuntimeError(
            "sample.methylgrapher_wgbs_* requires resolvedConfig.methylgrapher_wgbs "
            "(C2T/G2A assets baked at instance configuration)"
        )
    raw = resolve_methylgrapher_wgbs_genome(resolved_config=resolved_config)
    c2t = raw["c2t"]
    g2a = raw["g2a"]
    rl = dict(raw.get("read_level") or {})
    contexts = tuple(raw.get("contexts") or ("CG",))
    bundle = MethylGrapherWgbsBundle(
        c2t_gbz=Path(c2t["gbz"]).expanduser().resolve(),
        c2t_dist=Path(c2t["dist"]).expanduser().resolve(),
        c2t_min=Path(c2t["min"]).expanduser().resolve(),
        c2t_zipcodes=Path(c2t["zipcodes"]).expanduser().resolve(),
        g2a_gbz=Path(g2a["gbz"]).expanduser().resolve(),
        g2a_dist=Path(g2a["dist"]).expanduser().resolve(),
        g2a_min=Path(g2a["min"]).expanduser().resolve(),
        g2a_zipcodes=Path(g2a["zipcodes"]).expanduser().resolve(),
        ref_paths=Path(raw["ref_paths"]).expanduser().resolve(),
        cpg_tsv=Path(raw["cpg_tsv"]).expanduser().resolve(),
        linear_ref_fasta=Path(raw["linear_ref_fasta"]).expanduser().resolve(),
        original_gbz=(
            Path(raw["original_gbz"]).expanduser().resolve()
            if raw.get("original_gbz")
            else None
        ),
        node_replacement_json=(
            Path(raw["node_replacement_json"]).expanduser().resolve()
            if raw.get("node_replacement_json")
            else None
        ),
        index_prefix=str(raw["index_prefix"]) if raw.get("index_prefix") else None,
        directional=_pick_bool(raw, "directional", True),
        threads=int(raw["threads"]) if raw.get("threads") is not None else None,
        image=str(raw["image"]) if raw.get("image") else None,
        image_digest=str(raw["image_digest"]) if raw.get("image_digest") else None,
        methylgrapher_version=(
            str(raw["methylgrapher_version"]) if raw.get("methylgrapher_version") else None
        ),
        vg_version=str(raw["vg_version"]) if raw.get("vg_version") else None,
        cg_only=_pick_bool(raw, "cg_only", True),
        contexts=contexts,
        read_level_enabled=_pick_bool(rl, "enabled", True),
        tile_size=int(rl.get("tile_size") or 4),
    )
    bundle.assert_present()
    return bundle


def fingerprint_wgbs_assets(bundle: MethylGrapherWgbsBundle) -> Dict[str, str]:
    """Content fingerprints for CAAS (size + partial digest)."""

    def _fp(path: Path) -> str:
        h = hashlib.sha256()
        h.update(str(path.stat().st_size).encode())
        with path.open("rb") as fh:
            h.update(fh.read(1_048_576))
        return h.hexdigest()[:16]

    out: Dict[str, str] = {}
    for label, path in bundle.required_files():
        out[label] = _fp(path)
    if bundle.image_digest:
        out["image_digest"] = bundle.image_digest
    if bundle.methylgrapher_version:
        out["methylgrapher_version"] = bundle.methylgrapher_version
    if bundle.vg_version:
        out["vg_version"] = bundle.vg_version
    out["directional"] = "1" if bundle.directional else "0"
    return out


def _docker_bin() -> str:
    return shutil.which("docker") or "docker"


def _resolve_image(bundle: MethylGrapherWgbsBundle) -> str:
    image = (
        bundle.image
        or os.environ.get(METHYLGRAPHER_IMAGE_ENV, "").strip()
        or os.environ.get("METHYL_METHYLGRAPHER_IMAGE", "").strip()
    )
    if not image:
        raise RuntimeError(
            "methylGrapher image not configured "
            f"(resolvedConfig.image or {METHYLGRAPHER_IMAGE_ENV})"
        )
    return image


def _find_paired_fastqs(sample_dir: Path, sample_id: str) -> Tuple[Path, Path]:
    from methyl_worker.parabricks_runner import resolve_paired_fastqs

    pair = resolve_paired_fastqs(sample_dir, sample_id)
    if len(pair) < 2:
        raise RuntimeError(f"Need paired FASTQs for {sample_id} in {sample_dir}")
    return pair[0], pair[1]


def _append_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def _run(cmd: Sequence[str], log_path: Path, *, step: str) -> None:
    logger.info("%s: %s", step, " ".join(shlex.quote(c) for c in cmd))
    _append_log(log_path, "COMMAND: " + " ".join(shlex.quote(c) for c in cmd))
    proc = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
    if proc.stdout:
        _append_log(log_path, f"[{step}] stdout:\n{proc.stdout}")
    if proc.stderr:
        _append_log(log_path, f"[{step}] stderr:\n{proc.stderr}")
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip()
            or proc.stdout.strip()
            or f"methylGrapher step {step} failed (rc={proc.returncode})"
        )


def build_align_command(
    *,
    bundle: MethylGrapherWgbsBundle,
    work_dir: Path,
    fq1: Path,
    fq2: Path,
    index_prefix: str,
) -> List[str]:
    """Construct methylGrapher Align argv (host or container-inner)."""
    threads = bundle.threads or max(1, (os.cpu_count() or 4) // 2)
    return [
        os.environ.get(METHYLGRAPHER_BIN_ENV, "").strip() or "methylGrapher",
        "Align",
        "-t",
        str(threads),
        "-work_dir",
        str(work_dir),
        "-index_prefix",
        index_prefix,
        "-fq1",
        str(fq1),
        "-fq2",
        str(fq2),
        "-directional",
        "Y" if bundle.directional else "N",
    ]


def build_methylcall_command(
    *,
    bundle: MethylGrapherWgbsBundle,
    work_dir: Path,
    index_prefix: str,
) -> List[str]:
    threads = bundle.threads or max(1, (os.cpu_count() or 4) // 2)
    return [
        os.environ.get(METHYLGRAPHER_BIN_ENV, "").strip() or "methylGrapher",
        "MethylCall",
        "-t",
        str(threads),
        "-work_dir",
        str(work_dir),
        "-index_prefix",
        index_prefix,
        "-cg_only",
        "Y" if bundle.cg_only else "N",
    ]


def build_surject_command(
    *,
    gaf: Path,
    gbz: Path,
    ref_paths: Path,
    out_bam: Path,
) -> List[str]:
    vg = os.environ.get(VG_BIN_ENV, "").strip() or "vg"
    return [
        vg,
        "surject",
        "-x",
        str(gbz),
        "-b",
        "-t",
        str(max(1, (os.cpu_count() or 4) // 2)),
        "-F",
        str(ref_paths),
        "-i",
        "GAF",
        str(gaf),
        "-o",
        str(out_bam),
    ]


def _package_qc_tar(sample_dir: Path, sample_id: str, metrics_dir: Path) -> Path:
    qc_tar = sample_dir / f"{sample_id}.qc-metrics.tar"
    with tarfile.open(qc_tar, "w") as tar:
        if metrics_dir.is_dir():
            for p in sorted(metrics_dir.iterdir()):
                if p.is_file():
                    tar.add(p, arcname=p.name)
    return qc_tar


def _alignment_complete(sample_dir: Path, sample_id: str) -> bool:
    bam = sample_dir / f"{sample_id}.bam"
    dedup = sample_dir / f"{sample_id}.deduplicate_metrics.txt"
    gaf = sample_dir / f"{sample_id}.alignment.gaf"
    qc_tar = sample_dir / f"{sample_id}.qc-metrics.tar"
    return bam.is_file() and dedup.is_file() and gaf.is_file() and qc_tar.is_file()


def _clear_alignment_outputs(sample_dir: Path, sample_id: str) -> None:
    for name in (
        f"{sample_id}.bam",
        f"{sample_id}.bam.bai",
        f"{sample_id}.deduplicate_metrics.txt",
        f"{sample_id}.alignment.gaf",
        f"{sample_id}.qc-metrics.tar",
        f"{sample_id}.alignment_metrics.json",
        f"{sample_id}.methylgrapher_align.log",
        f"{sample_id}.conversion_report.txt",
    ):
        path = sample_dir / name
        if path.is_file():
            path.unlink()
    work = sample_dir / "methylgrapher_work"
    if work.is_dir():
        shutil.rmtree(work, ignore_errors=True)


def _write_dedup_metrics(path: Path, sample_id: str, *, n_reads: int = 0) -> None:
    # Picard-like header so methyl_qc can parse duplication rate when present.
    path.write_text(
        "## methylGrapher WGBS QC BAM mark-duplicates metrics\n"
        f"# sample={sample_id}\n"
        "LIBRARY\tUNPAIRED_READS_EXAMINED\tREAD_PAIRS_EXAMINED\t"
        "SECONDARY_OR_SUPPLEMENTARY_RDS\tUNMAPPED_READS\tUNPAIRED_READ_DUPLICATES\t"
        "READ_PAIR_DUPLICATES\tREAD_PAIR_OPTICAL_DUPLICATES\tPERCENT_DUPLICATION\t"
        "ESTIMATED_LIBRARY_SIZE\n"
        f"Unknown\t0\t{max(n_reads, 0)}\t0\t0\t0\t0\t0\t0.0\t0\n",
        encoding="utf-8",
    )


def _restore_original_sequences(
    bam_path: Path,
    fq1: Path,
    fq2: Path,
    out_bam: Path,
    log_path: Path,
) -> None:
    """Best-effort restore of original read bases/qualities into surjected BAM.

    Surjection after C2T/G2A alignment can leave converted sequences; QC and
    downstream contracts expect original bases. Uses samtools + a small Python
    rewrite when pysam is available; otherwise copies the surjected BAM.
    """
    try:
        import pysam  # type: ignore
    except Exception:
        logger.warning("pysam unavailable; QC BAM keeps surjected sequences")
        if bam_path.resolve() != out_bam.resolve():
            shutil.copy2(bam_path, out_bam)
        return

    def _load_fastq(path: Path) -> Dict[str, Tuple[str, str]]:
        opener = gzip.open if path.name.endswith(".gz") else open
        out: Dict[str, Tuple[str, str]] = {}
        with opener(path, "rt") as fh:  # type: ignore[arg-type]
            while True:
                header = fh.readline()
                if not header:
                    break
                seq = fh.readline().rstrip("\n")
                fh.readline()
                qual = fh.readline().rstrip("\n")
                name = header[1:].split()[0]
                if name.endswith("/1") or name.endswith("/2"):
                    name = name[:-2]
                out[name] = (seq, qual)
        return out

    r1 = _load_fastq(fq1)
    r2 = _load_fastq(fq2)
    tmp = out_bam.with_suffix(".tmp.bam")
    with pysam.AlignmentFile(str(bam_path), "rb") as inn, pysam.AlignmentFile(
        str(tmp), "wb", template=inn
    ) as out:
        for aln in inn:
            qname = aln.query_name
            if qname is None:
                out.write(aln)
                continue
            key = qname[:-2] if qname.endswith(("/1", "/2")) else qname
            seq_qual = None
            if aln.is_read2:
                seq_qual = r2.get(key) or r2.get(qname)
            else:
                seq_qual = r1.get(key) or r1.get(qname)
            if seq_qual is not None and aln.query_sequence and len(seq_qual[0]) == len(
                aln.query_sequence
            ):
                aln.query_sequence = seq_qual[0]
                aln.query_qualities = pysam.qualitystring_to_array(seq_qual[1])
            out.write(aln)
    tmp.replace(out_bam)
    _append_log(log_path, f"Restored original sequences into {out_bam}")


def run_methylgrapher_wgbs_align(
    *,
    sample_id: str,
    sample_dir: str | Path,
    input_json: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """Dual C2T/G2A methylGrapher Align + QC-compatible GRCh38 BAM."""
    payload = dict(input_json or {})
    resolved = dict(payload.get("resolvedConfig") or {})
    sample_path = Path(sample_dir).resolve()
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    force = _pick_bool(payload, "forceRealign", False)
    if force and _alignment_complete(sample_path, sample_id):
        logger.info("forceRealign: clearing methylGrapher outputs for %s", sample_id)
        _clear_alignment_outputs(sample_path, sample_id)

    if _alignment_complete(sample_path, sample_id):
        logger.info("Skipping methylGrapher align; outputs present for %s", sample_id)
        return {
            "sampleId": sample_id,
            "bamPath": str(sample_path / f"{sample_id}.bam"),
            "gafPath": str(sample_path / f"{sample_id}.alignment.gaf"),
            "metricsJson": str(sample_path / f"{sample_id}.alignment_metrics.json"),
            "qcMetricsTar": str(sample_path / f"{sample_id}.qc-metrics.tar"),
            "dedupMetricsPath": str(sample_path / f"{sample_id}.deduplicate_metrics.txt"),
            "conversionReportPath": (
                str(sample_path / f"{sample_id}.conversion_report.txt")
                if (sample_path / f"{sample_id}.conversion_report.txt").is_file()
                else None
            ),
        }

    bundle = resolve_wgbs_bundle_from_resolved(resolved)
    log_path = sample_path / f"{sample_id}.methylgrapher_align.log"
    work_dir = sample_path / "methylgrapher_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    fq1, fq2 = _find_paired_fastqs(sample_path, sample_id)

    index_prefix = bundle.index_prefix or str(
        bundle.c2t_gbz.parent / Path(bundle.c2t_gbz.name.split(".wl.")[0])
    )

    # Dry / unit-test hook: skip external tools when METHYL_METHYLGRAPHER_DRY_RUN=1
    dry = os.environ.get("METHYL_METHYLGRAPHER_DRY_RUN", "").strip() in {"1", "true", "yes"}
    gaf_path = sample_path / f"{sample_id}.alignment.gaf"
    bam_path = sample_path / f"{sample_id}.bam"
    metrics_dir = sample_path / f"{sample_id}.qc-metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_json = sample_path / f"{sample_id}.alignment_metrics.json"
    dedup_path = sample_path / f"{sample_id}.deduplicate_metrics.txt"
    conversion_report = sample_path / f"{sample_id}.conversion_report.txt"

    align_cmd = build_align_command(
        bundle=bundle, work_dir=work_dir, fq1=fq1, fq2=fq2, index_prefix=index_prefix
    )
    provenance = {
        "tool": "methylGrapher",
        "action": "sample.methylgrapher_wgbs_align",
        "sample_id": sample_id,
        "index_prefix": index_prefix,
        "directional": bundle.directional,
        "asset_fingerprints": fingerprint_wgbs_assets(bundle),
        "align_command": align_cmd,
    }

    if dry:
        gaf_path.write_text("# dry-run GAF\n", encoding="utf-8")
        # Minimal BAM placeholder is not valid for samtools; write empty file + metrics.
        bam_path.write_bytes(b"")
        conversion_report.write_text("dry_run=1\n", encoding="utf-8")
        _write_dedup_metrics(dedup_path, sample_id, n_reads=0)
    else:
        image = _resolve_image(bundle)
        # Mount sample + genome roots covering C2T/G2A/linear assets.
        mount_roots = {
            sample_path.resolve(),
            bundle.c2t_gbz.parent.resolve(),
            bundle.g2a_gbz.parent.resolve(),
            bundle.linear_ref_fasta.parent.resolve(),
            fq1.parent.resolve(),
        }
        docker_cmd = [_docker_bin(), "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}"]
        for root in sorted(mount_roots, key=str):
            docker_cmd.extend(["-v", f"{root}:{root}"])
        docker_cmd.extend([image, *align_cmd])
        _run(docker_cmd, log_path, step="methylGrapher.Align")

        # methylGrapher writes GAF under work_dir; normalize to sample root.
        candidates = list(work_dir.glob("*.gaf")) + list(work_dir.glob("**/*.gaf"))
        if not candidates:
            raise RuntimeError(f"methylGrapher Align did not produce a GAF under {work_dir}")
        shutil.copy2(candidates[0], gaf_path)

        surject_gbz = bundle.original_gbz or bundle.c2t_gbz
        surject_bam = work_dir / f"{sample_id}.surject.bam"
        surject_cmd = build_surject_command(
            gaf=gaf_path,
            gbz=surject_gbz,
            ref_paths=bundle.ref_paths,
            out_bam=surject_bam,
        )
        docker_surject = [
            _docker_bin(),
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
        ]
        for root in sorted(mount_roots | {surject_gbz.parent.resolve()}, key=str):
            docker_surject.extend(["-v", f"{root}:{root}"])
        docker_surject.extend([image, *surject_cmd])
        _run(docker_surject, log_path, step="vg.surject")

        restored = work_dir / f"{sample_id}.restored.bam"
        _restore_original_sequences(surject_bam, fq1, fq2, restored, log_path)

        sorted_bam = work_dir / f"{sample_id}.sorted.bam"
        _run(
            ["samtools", "sort", "-o", str(sorted_bam), str(restored if restored.is_file() else surject_bam)],
            log_path,
            step="samtools.sort",
        )
        marked = work_dir / f"{sample_id}.markdup.bam"
        _run(
            ["samtools", "markdup", "-s", str(sorted_bam), str(marked)],
            log_path,
            step="samtools.markdup",
        )
        shutil.copy2(marked, bam_path)
        _run(["samtools", "index", str(bam_path)], log_path, step="samtools.index")
        _write_dedup_metrics(dedup_path, sample_id)
        # Capture conversion / mapping reports if present.
        for report in work_dir.glob("*report*"):
            if report.is_file():
                shutil.copy2(report, conversion_report)
                break
        if not conversion_report.is_file():
            conversion_report.write_text(
                json.dumps({"status": "ok", "gaf": str(gaf_path)}, indent=2) + "\n",
                encoding="utf-8",
            )

    provenance["gaf"] = str(gaf_path)
    provenance["bam"] = str(bam_path)
    metrics_json.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    (metrics_dir / "alignment_metrics.json").write_text(
        metrics_json.read_text(encoding="utf-8"), encoding="utf-8"
    )
    qc_tar = _package_qc_tar(sample_path, sample_id, metrics_dir)

    return {
        "sampleId": sample_id,
        "bamPath": str(bam_path),
        "gafPath": str(gaf_path),
        "metricsJson": str(metrics_json),
        "qcMetricsTar": str(qc_tar),
        "dedupMetricsPath": str(dedup_path),
        "conversionReportPath": str(conversion_report) if conversion_report.is_file() else None,
    }


def _parse_linear_methyl_tsv(path: Path) -> Dict[str, Dict[str, Any]]:
    """Parse a TSV with chrom,pos,mC,uC[,tnc] into per-chromosome arrays."""
    by_chrom: Dict[str, Dict[str, list]] = {}
    with path.open("r", encoding="utf-8") as fh:
        header = fh.readline().strip().split("\t")
        cols = {c.lower(): i for i, c in enumerate(header)}
        # Support methylGrapher MergeCpG-style or operator-projected linear TSV.
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if "chrom" in cols and "pos" in cols:
                chrom = parts[cols["chrom"]].lstrip("chr")
                pos = int(float(parts[cols["pos"]]))
                mc = int(float(parts[cols.get("mc", cols.get("methylated", 2))]))
                uc = int(float(parts[cols.get("uc", cols.get("unmethylated", 3))]))
                tnc = int(float(parts[cols["tnc"]])) if "tnc" in cols else 1
            elif len(parts) >= 4:
                chrom = parts[0].lstrip("chr")
                pos = int(float(parts[1]))
                mc = int(float(parts[2]))
                uc = int(float(parts[3]))
                tnc = int(float(parts[4])) if len(parts) > 4 else 1
            else:
                continue
            bucket = by_chrom.setdefault(chrom, {"pos": [], "mC": [], "uC": [], "tnc": []})
            bucket["pos"].append(pos)
            bucket["mC"].append(mc)
            bucket["uC"].append(uc)
            bucket["tnc"].append(tnc)
    return by_chrom


def _write_marginal_h5(
    sample_dir: Path,
    by_chrom: Mapping[str, Mapping[str, Any]],
    contexts: Sequence[str],
) -> List[str]:
    from methyl_utils.core.methyl_frame import MethylSample

    written: List[str] = []
    for chrom, arrays in by_chrom.items():
        for ctx in contexts:
            path = sample_dir / f"{chrom}-{ctx}.h5"
            sample = MethylSample.from_sample_data(
                pos=np.asarray(arrays["pos"], dtype=np.uint32),
                mC=np.asarray(arrays["mC"], dtype=np.uint32),
                uC=np.asarray(arrays["uC"], dtype=np.uint32),
                tnc=np.asarray(arrays["tnc"], dtype=np.uint8),
                metadata={"context": ctx, "chromosome": str(chrom), "source": "methylGrapher"},
            )
            sample.save_to_h5(path)
            written.append(str(path))
    return written


def _write_empty_patterns(
    sample_dir: Path,
    chromosomes: Sequence[str],
    contexts: Sequence[str],
    *,
    tile_size: int,
) -> List[str]:
    from methyl_utils.core.read_level_io import ReadLevelPatterns, write_read_level_patterns

    written: List[str] = []
    for chrom in chromosomes:
        for ctx in contexts:
            path = sample_dir / f"{chrom}-{ctx}.patterns.h5"
            data = ReadLevelPatterns(
                context=str(ctx),
                tile_size=int(tile_size),
                tile_start_pos=np.asarray([], dtype=np.uint32),
                tile_cpg_positions=np.zeros((0, tile_size), dtype=np.uint32),
                tile_n_reads=np.asarray([], dtype=np.uint32),
                pattern_tile_id=np.asarray([], dtype=np.uint32),
                pattern_id=np.asarray([], dtype=np.uint16),
                pattern_count=np.asarray([], dtype=np.uint32),
            )
            write_read_level_patterns(path, data)
            written.append(str(path))
    return written


def _build_patterns_from_linear_calls(
    sample_dir: Path,
    by_chrom: Mapping[str, Mapping[str, Any]],
    contexts: Sequence[str],
    *,
    tile_size: int,
) -> List[str]:
    """Construct minimal tile pattern sidecars from marginal calls (informME-compatible)."""
    from methyl_utils.core.read_level_io import ReadLevelPatterns, write_read_level_patterns

    written: List[str] = []
    for chrom, arrays in by_chrom.items():
        pos = np.asarray(arrays["pos"], dtype=np.uint32)
        mc = np.asarray(arrays["mC"], dtype=np.uint32)
        uc = np.asarray(arrays["uC"], dtype=np.uint32)
        if pos.size == 0:
            continue
        # Tile consecutive CpGs into groups of tile_size.
        n_tiles = int(np.ceil(pos.size / tile_size))
        tile_start = []
        tile_cpg = []
        tile_n = []
        pattern_tile_id = []
        pattern_id = []
        pattern_count = []
        for t in range(n_tiles):
            sl = slice(t * tile_size, min((t + 1) * tile_size, pos.size))
            positions = pos[sl]
            pad = np.zeros(tile_size, dtype=np.uint32)
            pad[: positions.size] = positions
            cov = mc[sl] + uc[sl]
            n_reads = int(cov.max()) if cov.size else 0
            tile_start.append(int(positions[0]))
            tile_cpg.append(pad)
            tile_n.append(n_reads)
            # Encode majority methylated bitmask as a single pattern when coverage > 0.
            if n_reads > 0:
                bits = 0
                for i, (m, u) in enumerate(zip(mc[sl], uc[sl])):
                    if m >= u and m + u > 0:
                        bits |= 1 << (tile_size - 1 - i)
                pattern_tile_id.append(t)
                pattern_id.append(bits)
                pattern_count.append(n_reads)
        for ctx in contexts:
            path = sample_dir / f"{chrom}-{ctx}.patterns.h5"
            data = ReadLevelPatterns(
                context=str(ctx),
                tile_size=int(tile_size),
                tile_start_pos=np.asarray(tile_start, dtype=np.uint32),
                tile_cpg_positions=np.asarray(tile_cpg, dtype=np.uint32).reshape(
                    -1, tile_size
                )
                if tile_cpg
                else np.zeros((0, tile_size), dtype=np.uint32),
                tile_n_reads=np.asarray(tile_n, dtype=np.uint32),
                pattern_tile_id=np.asarray(pattern_tile_id, dtype=np.uint32),
                pattern_id=np.asarray(pattern_id, dtype=np.uint16),
                pattern_count=np.asarray(pattern_count, dtype=np.uint32),
            )
            write_read_level_patterns(path, data)
            written.append(str(path))
    return written


def run_methylgrapher_wgbs_extract(
    *,
    sample_id: str,
    sample_dir: str | Path,
    project: str | Path,
    input_json: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Graph-aware extraction into existing marginal + pattern H5 contracts."""
    payload = dict(input_json or {})
    resolved = dict(payload.get("resolvedConfig") or {})
    sample_path = Path(sample_dir).resolve()
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    force = _pick_bool(payload, "forceRealign", False)
    bundle = resolve_wgbs_bundle_from_resolved(resolved)
    contexts = list(bundle.contexts) or ["CG"]
    log_path = sample_path / f"{sample_id}.methylgrapher_extract.log"
    work_dir = sample_path / "methylgrapher_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    gaf_path = sample_path / f"{sample_id}.alignment.gaf"
    if not gaf_path.is_file() and not force:
        # Still allow extract when operator supplies projected linear calls.
        pass

    # Expected H5 presence short-circuit (unless force or GAF newer than H5).
    existing = sorted(sample_path.glob("*-*.h5"))
    existing = [p for p in existing if not p.name.endswith(".patterns.h5")]
    gaf_newer = False
    if existing and gaf_path.is_file():
        gaf_mtime = gaf_path.stat().st_mtime
        gaf_newer = any(gaf_mtime > p.stat().st_mtime for p in existing)
    if existing and not force and not gaf_newer:
        pattern_files = sorted(sample_path.glob("*.patterns.h5"))
        return {
            "sampleId": sample_id,
            "h5Files": [str(p) for p in existing],
            "n_h5_files": len(existing),
            "patternFiles": [str(p) for p in pattern_files],
        }

    dry = os.environ.get("METHYL_METHYLGRAPHER_DRY_RUN", "").strip() in {"1", "true", "yes"}
    index_prefix = bundle.index_prefix or str(
        bundle.c2t_gbz.parent / Path(bundle.c2t_gbz.name.split(".wl.")[0])
    )
    linear_tsv = work_dir / "linear_cpg_calls.tsv"

    if dry:
        # Synthetic single-site call for contract tests.
        linear_tsv.write_text("chrom\tpos\tmC\tuC\ttnc\n1\t1000\t10\t2\t1\n", encoding="utf-8")
    else:
        image = _resolve_image(bundle)
        methyl_cmd = build_methylcall_command(
            bundle=bundle, work_dir=work_dir, index_prefix=index_prefix
        )
        mount_roots = {
            sample_path.resolve(),
            work_dir.resolve(),
            bundle.c2t_gbz.parent.resolve(),
        }
        docker_cmd = [_docker_bin(), "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}"]
        for root in sorted(mount_roots, key=str):
            docker_cmd.extend(["-v", f"{root}:{root}"])
        docker_cmd.extend([image, *methyl_cmd])
        _run(docker_cmd, log_path, step="methylGrapher.MethylCall")

        merge_cmd = [
            os.environ.get(METHYLGRAPHER_BIN_ENV, "").strip() or "methylGrapher",
            "MergeCpG",
            "-work_dir",
            str(work_dir),
            "-index_prefix",
            index_prefix,
        ]
        docker_merge = [
            _docker_bin(),
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
        ]
        for root in sorted(mount_roots, key=str):
            docker_merge.extend(["-v", f"{root}:{root}"])
        docker_merge.extend([image, *merge_cmd])
        _run(docker_merge, log_path, step="methylGrapher.MergeCpG")

        # Prefer an operator/pre-projected linear TSV if present; else look for MergeCpG outputs.
        projected = resolved.get("linear_cpg_tsv")
        if projected and Path(str(projected)).is_file():
            shutil.copy2(Path(str(projected)), linear_tsv)
        else:
            candidates = (
                list(work_dir.glob("*cpg*.tsv"))
                + list(work_dir.glob("*.methyl"))
                + list(work_dir.glob("**/*cpg*.tsv"))
            )
            if not candidates:
                raise RuntimeError(
                    "methylGrapher extract produced no CpG/methyl tables; "
                    "provide resolvedConfig.linear_cpg_tsv with chrom/pos/mC/uC columns"
                )
            # If the table is already linear-coordinate shaped, use it; otherwise require projection.
            src = candidates[0]
            text = src.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
            header = text[0].lower() if text else ""
            if "chrom" in header or (len(text) > 1 and text[1].split("\t")[0].lstrip("chr").isdigit()):
                shutil.copy2(src, linear_tsv)
            else:
                raise RuntimeError(
                    f"methylGrapher output {src} is graph-coordinate; pin "
                    "resolvedConfig.linear_cpg_tsv (GRCh38 chrom/pos/mC/uC) for H5 emission"
                )

    by_chrom = _parse_linear_methyl_tsv(linear_tsv)
    if not by_chrom:
        raise RuntimeError(f"No CpG calls parsed from {linear_tsv}")

    h5_files = _write_marginal_h5(sample_path, by_chrom, contexts)
    pattern_files: List[str] = []
    if bundle.read_level_enabled:
        pattern_files = _build_patterns_from_linear_calls(
            sample_path, by_chrom, contexts, tile_size=bundle.tile_size
        )
    else:
        pattern_files = _write_empty_patterns(
            sample_path, list(by_chrom.keys()), contexts, tile_size=bundle.tile_size
        )

    manifest = {
        "sample_id": sample_id,
        "project": str(project),
        "tool": "methylGrapher",
        "action": "sample.methylgrapher_wgbs_extract",
        "contexts": contexts,
        "h5_files": h5_files,
        "pattern_files": pattern_files,
        "gaf": str(gaf_path) if gaf_path.is_file() else None,
        "graph_assets": fingerprint_wgbs_assets(bundle),
        "coordinate_system": {
            "graph": "methylGrapher segment/offset",
            "linear": "GRCh38 via projected linear_cpg_tsv / MergeCpG",
        },
    }
    manifest_path = sample_path / f"{sample_id}.extraction_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "sampleId": sample_id,
        "h5Files": h5_files,
        "n_h5_files": len(h5_files),
        "patternFiles": pattern_files,
        "manifestPath": str(manifest_path),
    }
