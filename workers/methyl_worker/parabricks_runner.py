"""NVIDIA Clara Parabricks fq2bam_meth alignment via Docker."""

from __future__ import annotations

import argparse
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

FASTQ_SUFFIXES: Sequence[str] = (".fastq.gz", ".fq.gz", ".fastq", ".fq")


@dataclass(frozen=True)
class ParabricksConfig:
    image: str
    gpu_flags: tuple[str, ...]
    bwa_threads: int
    extra_docker_args: tuple[str, ...]
    cleanup_tmp: bool


@dataclass(frozen=True)
class ParabricksPaths:
    sample_dir: Path
    sample_id: str
    reference_fasta: Path
    bam_path: Path
    qc_metrics_dir: Path
    qc_metrics_tar: Path
    metrics_json: Path
    dedup_metrics: Path
    log_path: Path
    tmp_dir: Path


def _load_config(
    *,
    parabricks_image: Optional[str] = None,
    bwa_threads: Optional[int] = None,
) -> ParabricksConfig:
    image = (parabricks_image or os.environ.get("METHYL_PARABRICKS_IMAGE", "")).strip()
    if not image:
        raise RuntimeError(
            "METHYL_PARABRICKS_IMAGE is required (e.g. nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1)"
        )

    gpu_raw = os.environ.get("METHYL_PARABRICKS_GPU_FLAGS", "--gpus all").strip()
    gpu_flags = tuple(shlex.split(gpu_raw)) if gpu_raw else ("--gpus", "all")

    threads = bwa_threads
    if threads is None:
        threads = int(os.environ.get("METHYL_PARABRICKS_BWA_THREADS", "16"))
    extra_raw = os.environ.get("METHYL_PARABRICKS_EXTRA_DOCKER_ARGS", "").strip()
    extra_docker_args = tuple(shlex.split(extra_raw)) if extra_raw else ()
    cleanup_tmp = os.environ.get("METHYL_PARABRICKS_CLEANUP_TMP", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    return ParabricksConfig(
        image=image,
        gpu_flags=gpu_flags,
        bwa_threads=threads,
        extra_docker_args=extra_docker_args,
        cleanup_tmp=cleanup_tmp,
    )


def _resolve_paths(sample_dir: Path, sample_id: str, reference_fasta: Path) -> ParabricksPaths:
    return ParabricksPaths(
        sample_dir=sample_dir,
        sample_id=sample_id,
        reference_fasta=reference_fasta.resolve(),
        bam_path=sample_dir / f"{sample_id}.bam",
        qc_metrics_dir=sample_dir / f"{sample_id}.qc-metrics",
        qc_metrics_tar=sample_dir / f"{sample_id}.qc-metrics.tar",
        metrics_json=sample_dir / f"{sample_id}.json",
        dedup_metrics=sample_dir / f"{sample_id}.deduplicate_metrics.txt",
        log_path=sample_dir / f"{sample_id}.fq2bam_meth.log",
        tmp_dir=sample_dir / "tmp",
    )


def _matches_fastq(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in FASTQ_SUFFIXES)


def _collect_fastqs(sample_dir: Path) -> List[Path]:
    found: List[Path] = []
    seen: set[Path] = set()
    for pattern in ("*.fastq.gz", "*.fq.gz", "*.fastq", "*.fq"):
        for match in sorted(sample_dir.glob(pattern)):
            if match.is_file() and match not in seen:
                seen.add(match)
                found.append(match)
        for match in sorted(sample_dir.glob(f"**/{pattern}")):
            if match.is_file() and match not in seen:
                seen.add(match)
                found.append(match)
    return sorted(found)


def resolve_paired_fastqs(sample_dir: Path, sample_id: str) -> List[Path]:
    """Return exactly two paired-end FASTQs for a sample."""
    explicit = [
        sample_dir / f"{sample_id}_1.fastq.gz",
        sample_dir / f"{sample_id}_2.fastq.gz",
    ]
    if all(p.is_file() for p in explicit):
        return explicit

    all_fastqs = [p for p in _collect_fastqs(sample_dir) if _matches_fastq(p)]
    if len(all_fastqs) == 2:
        return all_fastqs
    if len(all_fastqs) < 2:
        raise RuntimeError(f"Expected 2 FASTQ files under {sample_dir}, found {len(all_fastqs)}")
    raise RuntimeError(
        f"Expected exactly 2 FASTQ files under {sample_dir}, found {len(all_fastqs)}: "
        + ", ".join(p.name for p in all_fastqs)
    )


def _has_qc_artifact(paths: ParabricksPaths) -> bool:
    if paths.metrics_json.is_file():
        return True
    if paths.qc_metrics_tar.is_file():
        return True
    return paths.qc_metrics_dir.is_dir() and any(paths.qc_metrics_dir.iterdir())


def alignment_outputs_complete(paths: ParabricksPaths) -> bool:
    return paths.bam_path.is_file() and _has_qc_artifact(paths)


def _docker_bin() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker not found on PATH; required for Parabricks fq2bam_meth")
    return docker


def _build_docker_command(
    cfg: ParabricksConfig,
    paths: ParabricksPaths,
    fastqs: Sequence[Path],
) -> List[str]:
    genome_dir = paths.reference_fasta.parent
    ref_basename = paths.reference_fasta.name
    uid = os.getuid()
    gid = os.getgid()

    in_fq_args: List[str] = []
    for fastq in fastqs:
        rel = fastq.relative_to(paths.sample_dir)
        in_fq_args.append(f"/workdir/{rel.as_posix()}")

    cmd: List[str] = [
        _docker_bin(),
        "run",
        "--rm",
        *cfg.gpu_flags,
        "--user",
        f"{uid}:{gid}",
        "-v",
        f"{paths.sample_dir.resolve()}:/workdir",
        "-v",
        f"{paths.sample_dir.resolve()}:/outputdir",
        "-v",
        f"{genome_dir.resolve()}:/genomes:ro",
        "-w",
        "/workdir",
        *cfg.extra_docker_args,
        cfg.image,
        "pbrun",
        "fq2bam_meth",
        f"--ref=/genomes/{ref_basename}",
        "--in-fq",
        in_fq_args[0],
        in_fq_args[1],
        f"--out-bam=/outputdir/{paths.bam_path.name}",
        f"--out-qc-metrics-dir=/outputdir/{paths.qc_metrics_dir.name}",
        f"--out-duplicate-metrics=/outputdir/{paths.dedup_metrics.name}",
        f"--logfile=/outputdir/{paths.log_path.name}",
        f"--tmp-dir=/outputdir/{paths.tmp_dir.name}",
        f"--bwa-cpu-thread-pool={cfg.bwa_threads}",
        "--gpusort",
        "--gpuwrite",
    ]
    return cmd


def _append_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def _package_qc_metrics(paths: ParabricksPaths) -> Optional[Path]:
    if paths.qc_metrics_tar.is_file():
        return paths.qc_metrics_tar
    if not paths.qc_metrics_dir.is_dir():
        return None
    if not any(paths.qc_metrics_dir.iterdir()):
        return None

    with tarfile.open(paths.qc_metrics_tar, "w") as tar:
        tar.add(paths.qc_metrics_dir, arcname=paths.qc_metrics_dir.name)
    return paths.qc_metrics_tar


def _cleanup_tmp(paths: ParabricksPaths) -> None:
    if paths.tmp_dir.is_dir():
        shutil.rmtree(paths.tmp_dir, ignore_errors=True)


def run_fq2bam_meth(
    *,
    sample_id: str,
    sample_dir: str | Path,
    reference_fasta: str | Path,
    parabricks_image: Optional[str] = None,
    bwa_threads: Optional[int] = None,
) -> Dict[str, Optional[str]]:
    """Align bisulfite FASTQs with Parabricks fq2bam_meth in Docker."""
    sample_path = Path(sample_dir).resolve()
    reference_path = Path(reference_fasta).resolve()
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")
    if not reference_path.is_file():
        raise RuntimeError(f"referenceFasta not found: {reference_path}")

    cfg = _load_config(parabricks_image=parabricks_image, bwa_threads=bwa_threads)
    paths = _resolve_paths(sample_path, sample_id, reference_path)

    if alignment_outputs_complete(paths):
        logger.info("Skipping Parabricks; outputs already present for %s", sample_id)
        _package_qc_metrics(paths)
        return _result_payload(paths)

    fastqs = resolve_paired_fastqs(sample_path, sample_id)
    docker_cmd = _build_docker_command(cfg, paths, fastqs)
    paths.sample_dir.mkdir(parents=True, exist_ok=True)
    paths.tmp_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running Parabricks fq2bam_meth for %s", sample_id)
    _append_log(paths.log_path, "COMMAND: " + " ".join(shlex.quote(part) for part in docker_cmd))

    proc = subprocess.run(
        docker_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout:
        _append_log(paths.log_path, proc.stdout)
    if proc.stderr:
        _append_log(paths.log_path, proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip() or proc.stdout.strip() or "Parabricks fq2bam_meth failed"
        )

    if not paths.bam_path.is_file():
        raise RuntimeError(f"Parabricks did not produce BAM: {paths.bam_path}")

    tar_path = _package_qc_metrics(paths)
    if tar_path is None and not paths.metrics_json.is_file():
        raise RuntimeError(
            f"Parabricks did not produce QC metrics for {sample_id}: expected "
            f"{paths.qc_metrics_dir} or {paths.qc_metrics_tar}"
        )

    if cfg.cleanup_tmp:
        _cleanup_tmp(paths)

    return _result_payload(paths)


def _result_payload(paths: ParabricksPaths) -> Dict[str, Optional[str]]:
    metrics_json = str(paths.metrics_json) if paths.metrics_json.is_file() else None
    qc_tar = str(paths.qc_metrics_tar) if paths.qc_metrics_tar.is_file() else None
    return {
        "sampleId": paths.sample_id,
        "bamPath": str(paths.bam_path),
        "metricsJson": metrics_json,
        "qcMetricsTar": qc_tar,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Parabricks fq2bam_meth via Docker")
    parser.add_argument("sample_id", help="Sample identifier")
    parser.add_argument(
        "--sample-dir",
        help="Sample working directory (default: /work/samples/{sample_id})",
    )
    parser.add_argument(
        "--reference-fasta",
        help="Reference FASTA path (default: METHYL_REFERENCE_FASTA or GRCh38 under genomes dir)",
    )
    parser.add_argument("--image", help="Override METHYL_PARABRICKS_IMAGE")
    parser.add_argument("--bwa-threads", type=int, help="Override METHYL_PARABRICKS_BWA_THREADS")
    args = parser.parse_args(list(argv) if argv is not None else None)

    sample_dir = Path(
        args.sample_dir or os.environ.get("METHYL_SAMPLE_DIR") or f"/work/samples/{args.sample_id}"
    )
    reference = args.reference_fasta or os.environ.get("METHYL_REFERENCE_FASTA")
    if not reference:
        genomes_dir = Path(
            os.environ.get(
                "METHYL_GENOMES_DIR",
                "/work/genomes/human_genome/release-114",
            )
        )
        reference = str(genomes_dir / "Homo_sapiens.GRCh38.dna.primary_assembly.fa")

    result = run_fq2bam_meth(
        sample_id=args.sample_id,
        sample_dir=sample_dir,
        reference_fasta=reference,
        parabricks_image=args.image,
        bwa_threads=args.bwa_threads,
    )
    for key, value in result.items():
        if value is not None:
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
