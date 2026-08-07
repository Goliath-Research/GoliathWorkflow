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
    engine: str = "python"
    align_engine: str = "cpu_vg"
    cg_only: bool = True
    contexts: Tuple[str, ...] = ("CG",)
    read_level_enabled: bool = True
    tile_size: int = 4
    batch_size: Optional[int] = None
    linear_cpg_tsv: Optional[Path] = None
    wl_gfa: Optional[Path] = None

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


def _normalize_engine(value: Any) -> str:
    """Return ``python`` or ``mojo``; unset → ``python`` (safe default)."""
    if value is None or str(value).strip() == "":
        return "python"
    eng = str(value).strip().lower()
    if eng in {"mojo", "methylgrapher-mojo"}:
        return "mojo"
    if eng in {"python", "py", "0.2.0", "stock"}:
        return "python"
    raise RuntimeError(
        f"methylgrapher_wgbs.engine must be 'python' or 'mojo' (got {value!r})"
    )


def _normalize_align_engine(value: Any) -> str:
    """Return ``cpu_vg``, ``gpu_giraffe``, or ``mojo_giraffe``; unset → ``cpu_vg``."""
    if value is None or str(value).strip() == "":
        return "cpu_vg"
    eng = str(value).strip().lower()
    if eng in {"cpu_vg", "cpu", "vg"}:
        return "cpu_vg"
    if eng in {"mojo_giraffe", "mojo"}:
        return "mojo_giraffe"
    if eng in {"gpu_giraffe", "gpu", "gh200"}:
        return "gpu_giraffe"
    raise RuntimeError(
        "methylgrapher_wgbs.align_engine must be 'cpu_vg', 'gpu_giraffe', or "
        f"'mojo_giraffe' (got {value!r})"
    )


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
        engine=_normalize_engine(raw.get("engine")),
        align_engine=_normalize_align_engine(raw.get("align_engine")),
        cg_only=_pick_bool(raw, "cg_only", True),
        contexts=contexts,
        read_level_enabled=_pick_bool(rl, "enabled", True),
        tile_size=int(rl.get("tile_size") or 4),
        batch_size=int(raw["batch_size"]) if raw.get("batch_size") is not None else None,
        linear_cpg_tsv=(
            Path(str(raw["linear_cpg_tsv"])).expanduser().resolve()
            if raw.get("linear_cpg_tsv")
            else None
        ),
        wl_gfa=(
            Path(str(raw["wl_gfa"])).expanduser().resolve() if raw.get("wl_gfa") else None
        ),
    )
    bundle.assert_present()
    return bundle


# Stock python methylGrapher forks a second in-memory GFA worker when -t > 20;
# for HPRC-scale graphs that doubles RAM. Cap MethylCall threads for engine=python.
# engine=mojo forces gfa_worker_num=1, so this cap is not applied.
_METHYLCALL_THREAD_CAP = 16
_DEFAULT_MOJO_IMAGE = "epimethyl/methylgrapher:1.70-mojo"


def resolve_index_prefix(bundle: MethylGrapherWgbsBundle) -> str:
    index_prefix = bundle.index_prefix or str(
        bundle.c2t_gbz.parent / Path(bundle.c2t_gbz.name.split(".wl.")[0])
    )
    return str(Path(index_prefix).expanduser().resolve())


def resolve_wl_gfa_path(bundle: MethylGrapherWgbsBundle, index_prefix: str) -> Path:
    if bundle.wl_gfa is not None:
        return Path(bundle.wl_gfa)
    return Path(f"{index_prefix}.wl.gfa")


def assert_methylcall_assets(bundle: MethylGrapherWgbsBundle, index_prefix: str) -> Path:
    """Fail fast when MethylCall's required PrepareGenome artifacts are absent.

    Without ``{index_prefix}.wl.gfa``, methylGrapher's GFA workers crash while the
    alignment parser keeps filling an orphan queue — looks like a hang.
    """
    wl_gfa = resolve_wl_gfa_path(bundle, index_prefix)
    node_repl = Path(f"{index_prefix}.wl.node.replacement.json")
    if bundle.node_replacement_json is not None:
        node_repl = Path(bundle.node_replacement_json)
    missing: List[str] = []
    if not wl_gfa.is_file() or wl_gfa.stat().st_size == 0:
        missing.append(str(wl_gfa))
    if not node_repl.is_file() or node_repl.stat().st_size == 0:
        missing.append(str(node_repl))
    if missing:
        raise RuntimeError(
            "methylGrapher MethylCall requires PrepareGenome assets that are missing "
            "or empty: " + ", ".join(missing)
        )
    return wl_gfa


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
    out["engine"] = bundle.engine
    out["align_engine"] = bundle.align_engine
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
    if not image and bundle.engine == "mojo":
        image = _DEFAULT_MOJO_IMAGE
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


def _run(
    cmd: Sequence[str],
    log_path: Path,
    *,
    step: str,
    stdout_path: Path | None = None,
) -> None:
    """Run a command, optionally redirecting binary stdout to ``stdout_path``.

    When ``stdout_path`` is set (e.g. ``vg surject -b`` BAM), stdout is written
    as raw bytes and must not use ``text=True`` / ``capture_output``.
    """
    logger.info("%s: %s", step, " ".join(shlex.quote(c) for c in cmd))
    _append_log(log_path, "COMMAND: " + " ".join(shlex.quote(c) for c in cmd))
    if stdout_path is not None:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_path.open("wb") as out_fh:
            proc = subprocess.run(
                list(cmd),
                stdout=out_fh,
                stderr=subprocess.PIPE,
                check=False,
            )
        stderr_text = (proc.stderr or b"").decode("utf-8", errors="replace")
        if stderr_text:
            _append_log(log_path, f"[{step}] stderr:\n{stderr_text}")
        if proc.returncode != 0:
            raise RuntimeError(
                stderr_text.strip()
                or f"methylGrapher step {step} failed (rc={proc.returncode})"
            )
        if not stdout_path.is_file() or stdout_path.stat().st_size == 0:
            raise RuntimeError(f"{step} produced empty stdout file: {stdout_path}")
        return

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


def _effective_align_engine(bundle: MethylGrapherWgbsBundle) -> str:
    """Bundle align_engine, overridable by worker ``METHYLGRAPHER_ALIGN_ENGINE``.

    Fleet cutover: site/instance may still say ``cpu_vg`` while the host env
    pins ``gpu_giraffe`` / ``mojo_giraffe`` after publishing ``:1.70-mojo``.
    """
    env = os.environ.get("METHYLGRAPHER_ALIGN_ENGINE", "").strip()
    if env:
        return _normalize_align_engine(env)
    return bundle.align_engine


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
    cmd = [
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
        "-align_engine",
        _effective_align_engine(bundle),
    ]
    return cmd


def build_methylcall_command(
    *,
    bundle: MethylGrapherWgbsBundle,
    work_dir: Path,
    index_prefix: str,
) -> List[str]:
    threads = bundle.threads or max(1, (os.cpu_count() or 4) // 2)
    # Stock python dual-GFA cliff; mojo engine always uses a single GFA worker.
    if bundle.engine != "mojo" and threads > _METHYLCALL_THREAD_CAP:
        logger.warning(
            "MethylCall threads=%s exceeds safety cap %s (avoids dual in-memory GFA "
            "workers); clamping",
            threads,
            _METHYLCALL_THREAD_CAP,
        )
        threads = _METHYLCALL_THREAD_CAP
    cmd = [
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
    if bundle.batch_size is not None:
        cmd.extend(["-batch_size", str(int(bundle.batch_size))])
    return cmd


def build_qc_bam_command(
    *,
    bundle: MethylGrapherWgbsBundle,
    fq1_c2t: Path,
    fq2_g2a: Path,
    threads: int | None = None,
) -> List[str]:
    """Build ``vg giraffe`` argv emitting a GRCh38-surjected BAM on **stdout**.

    The QC BAM must not be produced by surjecting methylGrapher's GAF.
    methylGrapher aligns with ``vg giraffe --named-coordinates``, so the GAF path
    column holds GFA *segment* names, while ``vg surject -G`` reads that column as
    vg *node* IDs; the node lengths disagree and vg aborts on the first record
    (``cur_offset < cur_len`` assertion in ``gaf_to_alignment``). Re-mapping the
    converted reads with ``-o BAM --ref-paths`` keeps node space internal to vg.

    Only the primary R1-C2T / R2-G2A pass against the C2T graph is mapped: QC
    needs one best alignment per read, not methylGrapher's multi-graph output.
    """
    vg = os.environ.get(VG_BIN_ENV, "").strip() or "vg"
    n_threads = threads if threads is not None else max(1, (os.cpu_count() or 4) // 2)
    return [
        vg,
        "giraffe",
        "-p",
        "-t",
        str(n_threads),
        "-o",
        "BAM",
        "--ref-paths",
        str(bundle.ref_paths),
        "-Z",
        str(bundle.c2t_gbz),
        "-d",
        str(bundle.c2t_dist),
        "-m",
        str(bundle.c2t_min),
        "-z",
        str(bundle.c2t_zipcodes),
        "-f",
        str(fq1_c2t),
        "-f",
        str(fq2_g2a),
    ]


def _write_bs_converted_fastq(
    src: Path,
    dst: Path,
    *,
    base_from: str,
    base_to: str,
    log_path: Path,
) -> None:
    """Stream ``src`` into its in-silico bisulfite-converted form at ``dst``.

    Mirrors the conversion methylGrapher applies before ``vg giraffe`` (R1 C→T,
    R2 G→A for directional libraries), which it does not keep on disk. Only
    sequence lines are rewritten, so names and qualities stay intact and
    :func:`_restore_original_sequences` can put the original bases back.
    """
    if src.name.endswith(".gz"):
        reader = [("pigz" if shutil.which("pigz") else "gzip"), "-dc", str(src)]
    else:
        reader = ["cat", str(src)]
    convert = ["awk", f'NR % 4 == 2 {{ gsub(/{base_from}/, "{base_to}") }} 1']
    _append_log(
        log_path,
        "COMMAND: "
        + " ".join(shlex.quote(c) for c in reader)
        + " | "
        + " ".join(shlex.quote(c) for c in convert)
        + " > "
        + shlex.quote(str(dst)),
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as out_fh:
        rd = subprocess.Popen(reader, stdout=subprocess.PIPE)
        try:
            cv = subprocess.Popen(
                convert, stdin=rd.stdout, stdout=out_fh, stderr=subprocess.PIPE
            )
        finally:
            # Close our handle so the reader sees EPIPE if awk dies early.
            if rd.stdout is not None:
                rd.stdout.close()
        cv_err = (cv.communicate()[1] or b"").decode("utf-8", errors="replace")
        rc_reader = rd.wait()
    if rc_reader != 0 or cv.returncode != 0:
        raise RuntimeError(
            f"bisulfite conversion of {src.name} failed "
            f"(reader rc={rc_reader}, awk rc={cv.returncode}): {cv_err.strip()}"
        )
    if not dst.is_file() or dst.stat().st_size == 0:
        raise RuntimeError(f"bisulfite conversion produced empty FASTQ: {dst}")


def _flatten_qc_metrics_dir(metrics_dir: Path) -> None:
    """Copy nested metric files up to ``metrics_dir`` root for flat tar packaging.

    Parabricks ``collectmultiplemetrics`` may write under a subdirectory. Downstream
    ``_package_qc_tar`` only packs top-level files, and mode-aware QC looks up tables
    by basename suffix — so insert/GC/cycle/artifact files left nested would be
    omitted while ``quality_yield.txt`` alone could still mark collect as success.
    """
    if not metrics_dir.is_dir():
        return
    root = metrics_dir.resolve()
    for src in sorted(metrics_dir.rglob("*")):
        if not src.is_file():
            continue
        try:
            if src.resolve().parent == root:
                continue
        except OSError:
            continue
        dest = metrics_dir / src.name
        if dest.exists() and dest.resolve() == src.resolve():
            continue
        if dest.is_file() and dest.stat().st_size > 0 and dest.resolve() != src.resolve():
            # Prefer an existing non-empty root copy; do not clobber.
            continue
        shutil.copy2(src, dest)


def _package_qc_tar(sample_dir: Path, sample_id: str, metrics_dir: Path) -> Path:
    """Pack Picard metric text files into ``{sample_id}.qc-metrics.tar``.

    Files are added by basename (flat). Call ``_flatten_qc_metrics_dir`` first when
    collect may have written nested outputs.
    """
    qc_tar = sample_dir / f"{sample_id}.qc-metrics.tar"
    with tarfile.open(qc_tar, "w") as tar:
        if metrics_dir.is_dir():
            # Root-level files are authoritative (matches _flatten_qc_metrics_dir
            # no-clobber). Then add nested-only basenames as a safety net.
            seen: set[str] = set()
            try:
                root = metrics_dir.resolve()
            except OSError:
                root = metrics_dir
            for p in sorted(metrics_dir.iterdir(), key=lambda x: x.name):
                if not p.is_file() or p.name in seen:
                    continue
                seen.add(p.name)
                tar.add(p, arcname=p.name)
            for p in sorted(metrics_dir.rglob("*"), key=lambda x: (x.name, str(x))):
                if not p.is_file() or p.name in seen:
                    continue
                try:
                    if p.resolve().parent == root:
                        continue
                except OSError:
                    pass
                seen.add(p.name)
                tar.add(p, arcname=p.name)
    return qc_tar


def _maybe_collect_picard_metrics(
    *,
    sample_id: str,
    sample_path: Path,
    bam_path: Path,
    metrics_dir: Path,
    linear_ref_fasta: Path,
    log_path: Path,
    input_json: Optional[Mapping[str, Any]],
) -> bool:
    """Run ``pbrun collectmultiplemetrics`` on the WGBS QC BAM (soft-fail).

    Returns True when ``quality_yield.txt`` (or equivalent) lands under
    ``metrics_dir``. BS-converted BAM bases can skew artifact/GC metrics;
    these tables are operational screening only.
    """
    if not bam_path.is_file() or bam_path.stat().st_size == 0:
        logger.warning(
            "Skipping collectmultiplemetrics for %s: BAM missing or empty", sample_id
        )
        return False
    if not linear_ref_fasta.is_file():
        logger.warning(
            "Skipping collectmultiplemetrics for %s: linear_ref_fasta missing (%s)",
            sample_id,
            linear_ref_fasta,
        )
        return False

    try:
        from methyl_worker.giraffe_runner import _build_collect_metrics_docker_command
        from methyl_worker.parabricks_runner import (
            ParabricksPaths,
            resolve_parabricks_config,
        )
    except Exception as exc:  # pragma: no cover - import surface
        logger.warning("collectmultiplemetrics unavailable (import): %s", exc)
        return False

    try:
        cfg = resolve_parabricks_config(
            project_path=(input_json or {}).get("projectPath")
            or (input_json or {}).get("project"),
            input_json=input_json,
        )
    except Exception as exc:
        logger.warning(
            "Skipping collectmultiplemetrics for %s: Parabricks config unresolved (%s)",
            sample_id,
            exc,
        )
        return False

    metrics_dir.mkdir(parents=True, exist_ok=True)
    paths = ParabricksPaths(
        sample_dir=sample_path,
        sample_id=sample_id,
        reference_fasta=linear_ref_fasta,
        bam_path=bam_path,
        qc_metrics_dir=metrics_dir,
        qc_metrics_tar=sample_path / f"{sample_id}.qc-metrics.tar",
        metrics_json=sample_path / f"{sample_id}.json",
        dedup_metrics=sample_path / f"{sample_id}.deduplicate_metrics.txt",
        log_path=log_path,
        tmp_dir=sample_path / "tmp",
    )
    metrics_cmd = _build_collect_metrics_docker_command(cfg, paths, linear_ref_fasta)
    logger.info("Running Parabricks collectmultiplemetrics for WGBS QC BAM %s", sample_id)
    _append_log(log_path, "COMMAND: " + " ".join(shlex.quote(c) for c in metrics_cmd))
    try:
        _run(metrics_cmd, log_path, step="collectmultiplemetrics")
    except Exception as exc:
        logger.warning(
            "collectmultiplemetrics failed for %s (continuing with provenance-only QC): %s",
            sample_id,
            exc,
        )
        return False

    # Always flatten nested Parabricks outputs (not only when quality_yield is missing).
    _flatten_qc_metrics_dir(metrics_dir)
    qy = metrics_dir / "quality_yield.txt"
    if not qy.is_file():
        logger.warning(
            "collectmultiplemetrics produced no quality_yield.txt for %s", sample_id
        )
        return False
    return True


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


def _write_dedup_metrics(
    path: Path,
    sample_id: str,
    *,
    unpaired_examined: int = 0,
    read_pairs_examined: int = 0,
    unmapped_reads: int = 0,
    unpaired_duplicates: int = 0,
    read_pair_duplicates: int = 0,
    optical_duplicates: int = 0,
    percent_duplication: float = 0.0,
) -> None:
    """Write a Picard-shaped duplication metrics file methyl_qc can parse.

    The parser requires a ``METRICS CLASS`` header; a bare TSV is ignored and
    ``process_samples_to_qc_jsons`` then silently writes nothing.
    """
    path.write_text(
        "## methylGrapher WGBS QC BAM mark-duplicates metrics\n"
        f"## sample={sample_id}\n"
        "## METRICS CLASS\tpicard.sam.DuplicationMetrics\n"
        "LIBRARY\tUNPAIRED_READS_EXAMINED\tREAD_PAIRS_EXAMINED\t"
        "SECONDARY_OR_SUPPLEMENTARY_RDS\tUNMAPPED_READS\tUNPAIRED_READ_DUPLICATES\t"
        "READ_PAIR_DUPLICATES\tREAD_PAIR_OPTICAL_DUPLICATES\tPERCENT_DUPLICATION\t"
        "ESTIMATED_LIBRARY_SIZE\n"
        f"Unknown\t{unpaired_examined}\t{read_pairs_examined}\t0\t{unmapped_reads}\t"
        f"{unpaired_duplicates}\t{read_pair_duplicates}\t{optical_duplicates}\t"
        f"{percent_duplication:.6f}\t0\n",
        encoding="utf-8",
    )


def _dedup_metrics_from_markdup_stderr(stderr: str) -> Dict[str, float | int]:
    """Parse ``samtools markdup -s`` summary lines into Picard-ish counts."""
    stats: Dict[str, float | int] = {
        "unpaired_examined": 0,
        "read_pairs_examined": 0,
        "unmapped_reads": 0,
        "unpaired_duplicates": 0,
        "read_pair_duplicates": 0,
        "optical_duplicates": 0,
        "percent_duplication": 0.0,
    }
    written = 0
    dup_pair = 0
    dup_single = 0
    for line in stderr.splitlines():
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip().upper()
        try:
            value = int(rest.strip().split()[0])
        except (ValueError, IndexError):
            continue
        if key == "WRITTEN":
            written = value
        elif key == "DUPLICATE PAIR":
            dup_pair = value
        elif key == "DUPLICATE SINGLE":
            dup_single = value
        elif key == "DUPLICATE PAIR OPTICAL":
            stats["optical_duplicates"] = value
    # markdup -s reports per-read WRITTEN; approximate pair counts for Picard.
    stats["read_pairs_examined"] = max(written // 2, 0)
    stats["read_pair_duplicates"] = dup_pair
    stats["unpaired_duplicates"] = dup_single
    examined = max(int(stats["read_pairs_examined"]), 1)
    stats["percent_duplication"] = float(dup_pair) / float(examined)
    return stats


def _run_capturing_stderr(
    cmd: Sequence[str],
    log_path: Path,
    *,
    step: str,
) -> str:
    """Like :func:`_run` but return decoded stderr (for markdup -s summaries)."""
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
    return proc.stderr or ""


def _fastq_base_name(header_name: str) -> str:
    name = header_name.split()[0]
    if name.startswith("@"):
        name = name[1:]
    if name.endswith("/1") or name.endswith("/2"):
        name = name[:-2]
    return name


def _iter_fastq_records(path: Path):
    """Yield ``(base_name, seq, qual)`` without loading the full file."""
    try:
        from pysam import FastxFile  # type: ignore

        with FastxFile(str(path)) as fh:
            for rec in fh:
                yield _fastq_base_name(rec.name), rec.sequence, rec.quality or ""
            return
    except Exception:
        pass

    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt") as fh:  # type: ignore[arg-type]
        while True:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline().rstrip("\n")
            fh.readline()
            qual = fh.readline().rstrip("\n")
            yield _fastq_base_name(header[1:]), seq, qual


def _write_sorted_fastq_tsv(fastq: Path, out_tsv: Path, *, sort_dir: Path) -> None:
    """Stream FASTQ → ``name\\tseq\\tqual`` lines, externally sorted by name.

    Collation is ``LC_ALL=C`` lexicographic byte order — the same order as
    ``samtools sort -N`` (not natural ``-n``) and Python ``str`` comparisons used
    by the merge-join. Uses ``sort -S`` with a bounded memory budget so production
    WGBS FASTQs never materialize as Python dicts.
    """
    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    sort_dir.mkdir(parents=True, exist_ok=True)
    # Bound RAM for external sort; disk spill under sort_dir.
    sort_mem = os.environ.get("METHYL_FASTQ_SORT_MEM", "2G").strip() or "2G"
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    sort_cmd = [
        "sort",
        "-t",
        "\t",
        "-k1,1",
        "-S",
        sort_mem,
        "-T",
        str(sort_dir),
        "-o",
        str(out_tsv),
    ]
    proc = subprocess.Popen(
        sort_cmd,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdin is not None
    try:
        for name, seq, qual in _iter_fastq_records(fastq):
            proc.stdin.write(f"{name}\t{seq}\t{qual}\n")
        proc.stdin.close()
    except Exception:
        proc.kill()
        raise
    stderr = proc.stderr.read() if proc.stderr else ""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"external FASTQ sort failed (rc={rc}): {stderr.strip()}")


def _iter_sorted_fastq_tsv(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            yield parts[0], parts[1], parts[2]


def _bam_query_key(qname: str | None) -> str | None:
    if not qname:
        return None
    if qname.endswith("/1") or qname.endswith("/2"):
        return qname[:-2]
    return qname


def _restore_original_sequences(
    bam_path: Path,
    fq1: Path,
    fq2: Path,
    out_bam: Path,
    log_path: Path,
) -> None:
    """Restore original read bases/qualities into surjected BAM (streaming).

    Surjection after C2T/G2A alignment can leave converted sequences; QC expects
    original bases. Never loads full FASTQs into RAM: lexicographically name-sort
    the BAM (``samtools sort -N``), externally sort FASTQ records with matching
    ``LC_ALL=C`` collation, then merge-join by read name.

    Important: do **not** use ``samtools sort -n`` (natural/alpha-numeric order);
    that disagrees with Unix ``sort`` / Python ``str`` lexicographic order and
    silently drops restores for Illumina-style numeric read names.
    """
    try:
        import pysam  # type: ignore
    except Exception:
        logger.warning("pysam unavailable; QC BAM keeps surjected sequences")
        if bam_path.resolve() != out_bam.resolve():
            shutil.copy2(bam_path, out_bam)
        return

    work = out_bam.parent / f"{out_bam.stem}.restore_work"
    work.mkdir(parents=True, exist_ok=True)
    name_sorted_bam = work / "name_sorted.bam"
    r1_tsv = work / "r1.sorted.tsv"
    r2_tsv = work / "r2.sorted.tsv"
    sort_tmp = work / "sort_tmp"
    tmp_out = work / "restored.tmp.bam"

    try:
        # -N = lexicographic (raw) name order; matches LC_ALL=C sort + str comparisons.
        _run(
            ["samtools", "sort", "-N", "-o", str(name_sorted_bam), str(bam_path)],
            log_path,
            step="samtools.sort_name_lex",
        )
        _write_sorted_fastq_tsv(fq1, r1_tsv, sort_dir=sort_tmp / "r1")
        _write_sorted_fastq_tsv(fq2, r2_tsv, sort_dir=sort_tmp / "r2")

        r1_iter = _iter_sorted_fastq_tsv(r1_tsv)
        r2_iter = _iter_sorted_fastq_tsv(r2_tsv)
        r1_cur = next(r1_iter, None)
        r2_cur = next(r2_iter, None)

        def _advance(cur, it, key: str):
            """Advance sorted iterator until name >= key; consume match if equal.

            Both streams must use the same lexicographic collation.
            """
            while cur is not None and cur[0] < key:
                cur = next(it, None)
            if cur is not None and cur[0] == key:
                hit = cur
                cur = next(it, None)
                return cur, hit
            return cur, None

        n_restored = 0
        with pysam.AlignmentFile(str(name_sorted_bam), "rb") as inn, pysam.AlignmentFile(
            str(tmp_out), "wb", template=inn
        ) as out:
            for aln in inn:
                key = _bam_query_key(aln.query_name)
                if key is None or not aln.query_sequence:
                    out.write(aln)
                    continue
                if aln.is_read2:
                    r2_cur, hit = _advance(r2_cur, r2_iter, key)
                else:
                    r1_cur, hit = _advance(r1_cur, r1_iter, key)
                if hit is not None and len(hit[1]) == len(aln.query_sequence):
                    aln.query_sequence = hit[1]
                    aln.query_qualities = pysam.qualitystring_to_array(hit[2])
                    n_restored += 1
                out.write(aln)

        shutil.copy2(tmp_out, out_bam)
        _append_log(
            log_path,
            f"Restored original sequences into {out_bam} (n_restored={n_restored}, streaming merge-join)",
        )
    finally:
        # Keep work dir only when METHYL_KEEP_RESTORE_WORK=1 for debugging.
        if os.environ.get("METHYL_KEEP_RESTORE_WORK", "").strip() not in {
            "1",
            "true",
            "yes",
        }:
            shutil.rmtree(work, ignore_errors=True)


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
    # Resolve symlinks (/work -> …/Work) so Docker -v mounts and -index_prefix agree.
    index_prefix = str(Path(index_prefix).expanduser().resolve())
    work_dir = work_dir.resolve()
    fq1 = fq1.resolve()
    fq2 = fq2.resolve()

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
        _write_dedup_metrics(dedup_path, sample_id)
    else:
        image = _resolve_image(bundle)
        # Mount sample + genome roots covering C2T/G2A/linear assets.
        # Include resolved index_prefix parent so -index_prefix matches a mounted path.
        mount_roots = {
            sample_path.resolve(),
            work_dir,
            bundle.c2t_gbz.parent.resolve(),
            bundle.g2a_gbz.parent.resolve(),
            bundle.linear_ref_fasta.parent.resolve(),
            fq1.parent.resolve(),
            Path(index_prefix).parent,
        }
        if gaf_path.is_file() and gaf_path.stat().st_size > 0:
            # Resume: alignment is the longest step and the GAF only lands here
            # after methylGrapher succeeded, so never re-map it.
            logger.info("Reusing existing methylGrapher GAF for %s", sample_id)
            _append_log(log_path, f"REUSE: existing GAF {gaf_path}")
        else:
            docker_cmd = [
                _docker_bin(),
                "run",
                "--rm",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-e",
                f"METHYLGRAPHER_ALIGN_ENGINE={_effective_align_engine(bundle)}",
                "-e",
                "METHYLGRAPHER_GPU_GIRAFFE_FALLBACK="
                + (
                    os.environ.get("METHYLGRAPHER_GPU_GIRAFFE_FALLBACK", "mojo").strip()
                    or "mojo"
                ),
                "-e",
                "METHYLGRAPHER_GIRAFFE_DEVICE="
                + (os.environ.get("METHYLGRAPHER_GIRAFFE_DEVICE", "auto").strip() or "auto"),
                # Mojo runtime cache must be writable under --user (image /opt is root-owned).
                "-e",
                "MODULAR_CACHE_DIR="
                + (os.environ.get("MODULAR_CACHE_DIR", "").strip() or "/tmp/modular_cache"),
                "-e",
                "METHYLGRAPHER_MOJO_SEGMENTS_CACHE="
                + (
                    os.environ.get("METHYLGRAPHER_MOJO_SEGMENTS_CACHE", "").strip()
                    or "/work/cache/mojo_segments"
                ),
            ]
            cache_root = Path(
                os.environ.get("METHYLGRAPHER_MOJO_SEGMENTS_CACHE", "").strip()
                or "/work/cache/mojo_segments"
            )
            mount_roots.add(cache_root)
            # Also mount /work/cache parent when present so shared segment packs resolve.
            for extra in (Path("/work/cache"), Path("/lambda/nfs/Work/cache")):
                if extra.is_dir():
                    mount_roots.add(extra.resolve())
            for root in sorted(mount_roots, key=str):
                docker_cmd.extend(["-v", f"{root}:{root}"])
            docker_cmd.extend([image, *align_cmd])
            _run(docker_cmd, log_path, step="methylGrapher.Align")

            # methylGrapher merges to work_dir/alignment.gaf; ignore empty shard files
            # left behind by a failed prior attempt (alignment.0.gaf …).
            preferred = work_dir / "alignment.gaf"
            if preferred.is_file() and preferred.stat().st_size > 0:
                shutil.copy2(preferred, gaf_path)
            else:
                candidates = sorted(
                    (
                        p
                        for p in work_dir.glob("*.gaf")
                        if p.is_file() and p.stat().st_size > 0
                    ),
                    key=lambda p: p.stat().st_size,
                    reverse=True,
                )
                if not candidates:
                    raise RuntimeError(
                        f"methylGrapher Align did not produce a GAF under {work_dir}"
                    )
                shutil.copy2(candidates[0], gaf_path)

        if not bundle.directional:
            logger.warning(
                "non-directional library %s: QC BAM covers the R1-C2T/R2-G2A pass "
                "against the C2T graph only; methylation calls still use every "
                "methylGrapher pass",
                sample_id,
            )

        qc_bam = work_dir / f"{sample_id}.giraffe.bam"
        restored = work_dir / f"{sample_id}.restored.bam"
        if restored.is_file() and restored.stat().st_size > 0:
            # Resume after a failed fixmate/markdup: keep the name-ordered BAM.
            logger.info("Reusing restored QC BAM for %s", sample_id)
            _append_log(log_path, f"REUSE: existing restored BAM {restored}")
        else:
            if qc_bam.is_file() and qc_bam.stat().st_size > 0:
                logger.info("Reusing giraffe QC BAM for %s", sample_id)
                _append_log(log_path, f"REUSE: existing giraffe BAM {qc_bam}")
            else:
                c2t_r1 = work_dir / f"{sample_id}.C2T.R1.fastq"
                g2a_r2 = work_dir / f"{sample_id}.G2A.R2.fastq"
                _write_bs_converted_fastq(
                    fq1, c2t_r1, base_from="C", base_to="T", log_path=log_path
                )
                _write_bs_converted_fastq(
                    fq2, g2a_r2, base_from="G", base_to="A", log_path=log_path
                )
                qc_bam_cmd = build_qc_bam_command(
                    bundle=bundle,
                    fq1_c2t=c2t_r1,
                    fq2_g2a=g2a_r2,
                    threads=bundle.threads,
                )
                docker_qc_bam = [
                    _docker_bin(),
                    "run",
                    "--rm",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                ]
                for root in sorted(
                    mount_roots | {bundle.ref_paths.parent.resolve()}, key=str
                ):
                    docker_qc_bam.extend(["-v", f"{root}:{root}"])
                docker_qc_bam.extend([image, *qc_bam_cmd])
                # giraffe -o BAM writes to stdout; redirect as binary.
                _run(
                    docker_qc_bam, log_path, step="vg.giraffe_qc_bam", stdout_path=qc_bam
                )
                for converted in (c2t_r1, g2a_r2):
                    converted.unlink(missing_ok=True)

            _restore_original_sequences(qc_bam, fq1, fq2, restored, log_path)

        # Restored BAM is name-ordered (merge-join walks a -N sorted stream).
        # fixmate must see that order so markdup gets the MC/ms tags it needs.
        fixed = work_dir / f"{sample_id}.fixmate.bam"
        _run(
            [
                "samtools",
                "fixmate",
                "-m",
                str(restored if restored.is_file() else qc_bam),
                str(fixed),
            ],
            log_path,
            step="samtools.fixmate",
        )
        sorted_bam = work_dir / f"{sample_id}.sorted.bam"
        _run(
            ["samtools", "sort", "-o", str(sorted_bam), str(fixed)],
            log_path,
            step="samtools.sort",
        )
        marked = work_dir / f"{sample_id}.markdup.bam"
        markdup_stderr = _run_capturing_stderr(
            ["samtools", "markdup", "-s", str(sorted_bam), str(marked)],
            log_path,
            step="samtools.markdup",
        )
        shutil.copy2(marked, bam_path)
        _run(["samtools", "index", str(bam_path)], log_path, step="samtools.index")
        _write_dedup_metrics(
            dedup_path, sample_id, **_dedup_metrics_from_markdup_stderr(markdup_stderr)
        )
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

    picard_ok = False
    if not dry:
        picard_ok = _maybe_collect_picard_metrics(
            sample_id=sample_id,
            sample_path=sample_path,
            bam_path=bam_path,
            metrics_dir=metrics_dir,
            linear_ref_fasta=bundle.linear_ref_fasta,
            log_path=log_path,
            input_json=payload,
        )
    provenance["collectmultiplemetrics"] = bool(picard_ok)
    if picard_ok:
        provenance["picard_qc_note"] = (
            "Picard CollectMultipleMetrics on restored QC BAM; BS chemistry may "
            "skew artifact/GC metrics — operational screening only."
        )

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


def _is_grch38_sample(name: str) -> bool:
    """True when a PanSN sample name denotes the GRCh38 linear reference."""
    head = name.strip().split("#", 1)[0].upper()
    return head == "HG38" or head.startswith("GRCH38")


def _normalize_grch38_chrom(name: str) -> Optional[str]:
    """Map path/sequence names like ``GRCh38#0#chr1`` / ``chr1`` → ``1``."""
    raw = str(name).strip()
    if not raw:
        return None
    # Prefer GRCh38 haplotype paths; ignore CHM13 / sample haplotypes.
    if "#" in raw:
        if not _is_grch38_sample(raw):
            return None
        raw = raw.split("#")[-1]
    if raw.lower().startswith("chr"):
        raw = raw[3:]
    if raw.upper() == "M":
        return "MT"
    if raw in {"X", "Y", "MT"} or raw.isdigit():
        return raw
    return None


def build_grch38_segment_offsets_from_gfa(
    gfa_path: Path,
) -> Dict[str, Tuple[str, int, int, str]]:
    """Map segment ID → (chrom, start_0based, length, orient) for GRCh38 paths.

    Parses GFA ``W`` / ``P`` lines. When a segment appears on multiple GRCh38
    paths, the first occurrence wins (stable for primary chromosomes).
    ``orient`` is ``'>'`` or ``'<'`` for the walk step used.
    """
    import re

    seg_re = re.compile(r"([><])([^><]+)")
    offsets: Dict[str, Tuple[str, int, int, str]] = {}
    # Cache segment lengths from S-lines so W-path walks can advance.
    seg_len: Dict[str, int] = {}

    with gfa_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line or line[0] not in "SWP":
                continue
            if line[0] == "S":
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) < 3:
                    continue
                seg_id, seq = parts[1], parts[2]
                if seq == "*":
                    # length may be in LN:i: tag
                    length = 0
                    for tag in parts[3:]:
                        if tag.startswith("LN:i:"):
                            length = int(tag[5:])
                            break
                    seg_len[seg_id] = length
                else:
                    seg_len[seg_id] = len(seq)
                continue

            parts = line.rstrip("\r\n").split("\t")
            path_seq = ""
            chrom: Optional[str] = None
            path_start = 0
            if line[0] == "W" and len(parts) >= 7:
                # W SampleId HapIndex SeqId SeqStart SeqEnd Walk
                # SeqId is usually a bare chromosome name, so the sample field is
                # the only place the haplotype is identified.
                if not _is_grch38_sample(parts[1]):
                    continue
                chrom = _normalize_grch38_chrom(parts[3])
                if chrom is None:
                    continue
                try:
                    path_start = int(parts[4])
                except ValueError:
                    path_start = 0
                path_seq = parts[6]
            elif line[0] == "P" and len(parts) >= 3:
                chrom = _normalize_grch38_chrom(parts[1])
                if chrom is None:
                    continue
                # P pathName seg+[,seg+]…
                path_seq = "".join(
                    (">" if tok.endswith("+") else "<") + tok[:-1]
                    for tok in parts[2].split(",")
                    if tok
                )
            else:
                continue

            cursor = path_start
            for m in seg_re.finditer(path_seq):
                orient, seg_id = m.group(1), m.group(2)
                length = int(seg_len.get(seg_id, 0))
                if seg_id not in offsets:
                    offsets[seg_id] = (chrom, cursor, length, orient)
                cursor += length
    return offsets


def _genomic_pos_1based(
    *,
    base_0: int,
    seg_len: int,
    orient: str,
    pos_0: int,
) -> int:
    """Convert 0-based segment offset to 1-based linear genomic coordinate."""
    if orient == "<":
        if seg_len <= 0:
            g0 = base_0 + int(pos_0)
        else:
            g0 = base_0 + (int(seg_len) - 1 - int(pos_0))
    else:
        g0 = base_0 + int(pos_0)
    return g0 + 1


def project_graph_cpg_to_linear_tsv(
    *,
    graph_cpg_tsv: Path,
    cpg_registry_tsv: Path,
    segment_offsets: Mapping[str, Tuple],
    out_tsv: Path,
) -> int:
    """Join MergeCpG ``graph.cpg.tsv`` to ``cpg.tsv`` and emit chrom/pos/mC/uC.

    Emits **1-based** GRCh38 coordinates (MethylExtractor / linear H5 convention).
    ``segment_offsets`` values are ``(chrom, start_0based[, length, orient])``.
    Sites whose cytosines are not on a GRCh38 reference path are skipped.
    Duplicate linear positions are aggregated (sum mC/uC).
    Returns the number of projected rows written.
    """
    # cpg.tsv: C0\tseg1\tpos1\tseg2\tpos2\ttag...
    registry: Dict[str, Tuple[str, int, str, int]] = {}
    with cpg_registry_tsv.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 5:
                continue
            # First field is like C0 / E12 (letter glued to index).
            cpg_id = parts[0]
            try:
                registry[cpg_id] = (parts[1], int(parts[2]), parts[3], int(parts[4]))
            except ValueError:
                continue

    # Aggregate in case multiple graph CpGs project to the same linear locus.
    agg: Dict[Tuple[str, int], List[int]] = {}
    with graph_cpg_tsv.open("r", encoding="utf-8", errors="replace") as fin:
        for line in fin:
            if not line.strip():
                continue
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 3:
                continue
            cpg_id, met_s, cov_s = parts[0], parts[1], parts[2]
            if cpg_id not in registry:
                continue
            try:
                met = int(float(met_s))
                cov = int(float(cov_s))
            except ValueError:
                continue
            if cov <= 0:
                continue
            seg1, pos1, seg2, pos2 = registry[cpg_id]
            # Prefer the first cytosine on a GRCh38 path.
            chrom_pos: Optional[Tuple[str, int]] = None
            for seg, pos in ((seg1, pos1), (seg2, pos2)):
                if seg not in segment_offsets:
                    continue
                entry = segment_offsets[seg]
                chrom = str(entry[0])
                base = int(entry[1])
                if len(entry) >= 4:
                    slen = int(entry[2])
                    orient = str(entry[3]) if entry[3] in (">", "<") else ">"
                elif len(entry) == 3 and str(entry[2]) in (">", "<"):
                    slen = 0
                    orient = str(entry[2])
                else:
                    slen = int(entry[2]) if len(entry) >= 3 else 0
                    orient = ">"
                chrom_pos = (chrom, _genomic_pos_1based(base_0=base, seg_len=slen, orient=orient, pos_0=int(pos)))
                break
            if chrom_pos is None:
                continue
            chrom, pos = chrom_pos
            uc = max(0, cov - met)
            key = (chrom, pos)
            cur = agg.get(key)
            if cur is None:
                agg[key] = [met, uc]
            else:
                cur[0] += met
                cur[1] += uc

    with out_tsv.open("w", encoding="utf-8") as fout:
        fout.write("chrom\tpos\tmC\tuC\ttnc\n")
        for (chrom, pos), (met, uc) in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            fout.write(f"{chrom}\t{pos}\t{met}\t{uc}\t1\n")
    return len(agg)


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
    """Write MethylExtractor-compatible structured ``methylation_data`` datasets.

    Uses gzip (not Zstd plugin) so QC tools can read without ``HDF5_PLUGIN_PATH``.
    Widens mC/uC to uint32 when counts exceed uint16.
    """
    import h5py

    written: List[str] = []
    for chrom, arrays in by_chrom.items():
        for ctx in contexts:
            path = sample_dir / f"{chrom}-{ctx}.h5"
            pos = np.asarray(arrays["pos"], dtype=np.uint32)
            mc = np.asarray(arrays["mC"], dtype=np.int64)
            uc = np.asarray(arrays["uC"], dtype=np.int64)
            tnc = np.asarray(arrays.get("tnc", np.ones(pos.size, dtype=np.uint8)), dtype=np.uint8)
            if mc.size and (int(mc.max()) > 65535 or int(uc.max()) > 65535):
                dt = np.dtype([("pos", "<u4"), ("mC", "<u4"), ("uC", "<u4"), ("tnc", "u1")])
                data = np.empty(pos.size, dtype=dt)
                data["pos"] = pos
                data["mC"] = mc.astype(np.uint32)
                data["uC"] = uc.astype(np.uint32)
                data["tnc"] = tnc
            else:
                dt = np.dtype([("pos", "<u4"), ("mC", "<u2"), ("uC", "<u2"), ("tnc", "u1")])
                data = np.empty(pos.size, dtype=dt)
                data["pos"] = pos
                data["mC"] = mc.astype(np.uint16, copy=False)
                data["uC"] = uc.astype(np.uint16, copy=False)
                data["tnc"] = tnc
            with h5py.File(path, "w") as handle:
                handle.create_dataset(
                    "methylation_data", data=data, compression="gzip", compression_opts=4
                )
                handle.attrs["context"] = str(ctx)
                handle.attrs["chromosome"] = str(chrom)
                handle.attrs["source"] = "methylGrapher"
            written.append(str(path))
    return written


def _context_metrics_from_calls(arrays: Mapping[str, Any]) -> Dict[str, Any]:
    """Per-chromosome/context metrics for extraction-QC manifests."""
    mc = np.asarray(arrays.get("mC", []), dtype=np.float64)
    uc = np.asarray(arrays.get("uC", []), dtype=np.float64)
    if mc.size == 0:
        return {
            "num_positions": 0,
            "methylation_level": None,
            "mean_coverage": 0.0,
            "total_coverage": 0.0,
        }
    cov = mc + uc
    total_cov = float(cov.sum())
    mean_cov = float(cov.mean())
    meth = float(mc.sum() / total_cov) if total_cov > 0 else None
    return {
        "num_positions": int(mc.size),
        "methylation_level": meth,
        "mean_coverage": mean_cov,
        "total_coverage": total_cov,
    }


def build_canonical_extraction_manifest(
    *,
    sample_id: str,
    project: str | Path,
    by_chrom: Mapping[str, Mapping[str, Any]],
    contexts: Sequence[str],
    h5_files: Sequence[str],
    pattern_files: Sequence[str],
    gaf_path: Optional[Path],
    graph_assets: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build an extraction manifest compatible with ``methyl_extraction_qc``.

    Emits the canonical ``metadata`` / ``summary`` / ``per_chromosome`` blocks
    expected by extraction QC guardrails, plus methylGrapher provenance
    (graph assets, coordinate system, H5/pattern paths). Read-filtering stats
    are omitted when unavailable so the discard-fraction guardrail reports a
    skipped check rather than inventing values.
    """
    contexts_list = [str(c) for c in contexts] or ["CG"]
    per_chromosome: Dict[str, Dict[str, Any]] = {}
    weighted_cov_num = 0.0
    weighted_cov_den = 0.0
    weighted_meth_num = 0.0
    weighted_meth_den = 0.0
    ctx_meth_totals: Dict[str, List[float]] = {c: [0.0, 0.0] for c in contexts_list}

    for chrom, arrays in by_chrom.items():
        chrom_key = str(chrom).lstrip("chr")
        chrom_entry: Dict[str, Any] = {}
        metrics = _context_metrics_from_calls(arrays)
        for ctx in contexts_list:
            # Linear MergeCpG / projected TSV is currently CpG-shaped; replicate
            # the same site metrics under each requested context for QC completeness.
            chrom_entry[ctx] = {
                "num_positions": metrics["num_positions"],
                "methylation_level": metrics["methylation_level"],
                "mean_coverage": metrics["mean_coverage"],
            }
            if ctx == "CG" and metrics["num_positions"]:
                weighted_cov_num += float(metrics["mean_coverage"]) * float(metrics["num_positions"])
                weighted_cov_den += float(metrics["num_positions"])
                if metrics["methylation_level"] is not None:
                    weighted_meth_num += float(metrics["methylation_level"]) * float(
                        metrics["total_coverage"]
                    )
                    weighted_meth_den += float(metrics["total_coverage"])
            mc = np.asarray(arrays.get("mC", []), dtype=np.float64)
            uc = np.asarray(arrays.get("uC", []), dtype=np.float64)
            ctx_meth_totals[ctx][0] += float(mc.sum()) if mc.size else 0.0
            ctx_meth_totals[ctx][1] += float((mc + uc).sum()) if mc.size else 0.0
        per_chromosome[chrom_key] = chrom_entry

    cpg_weighted_mean_coverage = (
        weighted_cov_num / weighted_cov_den if weighted_cov_den > 0 else 0.0
    )
    cpg_methylation_level = (
        weighted_meth_num / weighted_meth_den if weighted_meth_den > 0 else None
    )
    summary: Dict[str, Any] = {
        "cpg_weighted_mean_coverage": cpg_weighted_mean_coverage,
        "cpg_methylation_level": cpg_methylation_level,
        "n_chromosomes": len(per_chromosome),
        "n_h5_files": len(h5_files),
        "n_pattern_files": len(pattern_files),
    }
    for ctx in contexts_list:
        if ctx == "CG":
            continue
        meth_num, meth_den = ctx_meth_totals[ctx]
        key = f"{ctx.lower()}_methylation_level"
        summary[key] = (meth_num / meth_den) if meth_den > 0 else None

    return {
        "metadata": {
            "schema_name": "methylextractor.extraction_manifest",
            "schema_version": "1.0.0",
            "sample_id": sample_id,
            "contexts_extracted": contexts_list,
            "extractor": "methylGrapher",
            "action": "sample.methylgrapher_wgbs_extract",
        },
        "summary": summary,
        "per_chromosome": per_chromosome,
        # Provenance retained for operators / archive; not required by guardrails.
        "sample_id": sample_id,
        "project": str(project),
        "tool": "methylGrapher",
        "action": "sample.methylgrapher_wgbs_extract",
        "contexts": contexts_list,
        "h5_files": list(h5_files),
        "pattern_files": list(pattern_files),
        "gaf": str(gaf_path) if gaf_path is not None and gaf_path.is_file() else None,
        "graph_assets": dict(graph_assets),
        "coordinate_system": {
            "graph": "methylGrapher segment/offset",
            "linear": "GRCh38 via projected linear_cpg_tsv / MergeCpG",
        },
    }


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
    index_prefix = resolve_index_prefix(bundle)
    work_dir = work_dir.resolve()
    linear_tsv = work_dir / "linear_cpg_calls.tsv"

    if dry:
        # Synthetic single-site call for contract tests.
        linear_tsv.write_text("chrom\tpos\tmC\tuC\ttnc\n1\t1000\t10\t2\t1\n", encoding="utf-8")
    else:
        wl_gfa = assert_methylcall_assets(bundle, index_prefix)
        # Ensure work_dir has alignment.gaf (methylGrapher MethylCall hardcodes this name).
        work_gaf = work_dir / "alignment.gaf"
        if not work_gaf.is_file() and gaf_path.is_file():
            if gaf_path.resolve() != work_gaf.resolve():
                shutil.copy2(gaf_path, work_gaf)

        image = _resolve_image(bundle)
        methyl_cmd = build_methylcall_command(
            bundle=bundle, work_dir=work_dir, index_prefix=index_prefix
        )
        mount_roots = {
            sample_path.resolve(),
            work_dir,
            bundle.c2t_gbz.parent.resolve(),
            Path(index_prefix).parent,
            wl_gfa.resolve().parent,
        }
        # Follow symlink targets so Docker can open {index_prefix}.wl.gfa on local disk.
        if wl_gfa.is_symlink():
            mount_roots.add(wl_gfa.resolve().parent)
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

        # Prefer an operator/pre-projected linear TSV if present; else project MergeCpG.
        projected = resolved.get("linear_cpg_tsv") or (
            str(bundle.linear_cpg_tsv) if bundle.linear_cpg_tsv else None
        )
        if projected and Path(str(projected)).is_file():
            shutil.copy2(Path(str(projected)), linear_tsv)
        else:
            graph_cpg = work_dir / "graph.cpg.tsv"
            if not graph_cpg.is_file():
                candidates = list(work_dir.glob("*cpg*.tsv")) + list(
                    work_dir.glob("**/*cpg*.tsv")
                )
                if not candidates:
                    raise RuntimeError(
                        "methylGrapher MergeCpG produced no graph.cpg.tsv; "
                        "provide resolvedConfig.linear_cpg_tsv with chrom/pos/mC/uC columns"
                    )
                graph_cpg = candidates[0]
            # Already linear?
            peek = graph_cpg.read_text(encoding="utf-8", errors="replace").splitlines()[:3]
            header = peek[0].lower() if peek else ""
            if "chrom" in header and "pos" in header:
                shutil.copy2(graph_cpg, linear_tsv)
            else:
                logger.info(
                    "Projecting graph CpGs onto GRCh38 paths from %s", wl_gfa
                )
                offsets = build_grch38_segment_offsets_from_gfa(wl_gfa)
                if not offsets:
                    raise RuntimeError(
                        f"No GRCh38 path offsets parsed from {wl_gfa}; cannot project "
                        "graph.cpg.tsv — pin resolvedConfig.linear_cpg_tsv"
                    )
                n = project_graph_cpg_to_linear_tsv(
                    graph_cpg_tsv=graph_cpg,
                    cpg_registry_tsv=bundle.cpg_tsv,
                    segment_offsets=offsets,
                    out_tsv=linear_tsv,
                )
                if n <= 0:
                    raise RuntimeError(
                        "graph→GRCh38 projection wrote 0 sites (no called CpGs on "
                        f"GRCh38 paths). graph_cpg={graph_cpg} wl_gfa={wl_gfa}"
                    )
                logger.info("Projected %s graph CpG sites to %s", n, linear_tsv)

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

    manifest = build_canonical_extraction_manifest(
        sample_id=sample_id,
        project=project,
        by_chrom=by_chrom,
        contexts=contexts,
        h5_files=h5_files,
        pattern_files=pattern_files,
        gaf_path=gaf_path if gaf_path.is_file() else None,
        graph_assets=fingerprint_wgbs_assets(bundle),
    )
    manifest_path = sample_path / f"{sample_id}.extraction_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "sampleId": sample_id,
        "h5Files": h5_files,
        "n_h5_files": len(h5_files),
        "patternFiles": pattern_files,
        "manifestPath": str(manifest_path),
    }
