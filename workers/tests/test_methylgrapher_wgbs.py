"""Unit tests for methylGrapher WGBS pangenome SamplePrep path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_utils.action_config_resolver import resolve_methylgrapher_wgbs_genome
from methyl_worker.methylgrapher_wgbs_runner import (
    _flatten_qc_metrics_dir,
    _package_qc_tar,
    _restore_original_sequences,
    _run,
    _write_bs_converted_fastq,
    assert_methylcall_assets,
    build_align_command,
    build_grch38_segment_offsets_from_gfa,
    build_methylcall_command,
    build_qc_bam_command,
    project_graph_cpg_to_linear_tsv,
    resolve_wgbs_bundle_from_resolved,
    run_methylgrapher_wgbs_align,
    run_methylgrapher_wgbs_extract,
)
from methyl_worker.task_models.sample_prep_models import (
    MethylGrapherWgbsAlignTaskInput,
    MethylGrapherWgbsExtractTaskInput,
    MethylGrapherWgbsStepConfig,
)


def _touch_bundle(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "c2t": {
            "gbz": root / "c2t.gbz",
            "dist": root / "c2t.dist",
            "min": root / "c2t.min",
            "zipcodes": root / "c2t.zip",
        },
        "g2a": {
            "gbz": root / "g2a.gbz",
            "dist": root / "g2a.dist",
            "min": root / "g2a.min",
            "zipcodes": root / "g2a.zip",
        },
        "ref_paths": root / "ref.paths",
        "cpg_tsv": root / "cpg.tsv",
        "linear_ref_fasta": root / "GRCh38.fa",
        "original_gbz": root / "orig.gbz",
        "index_prefix": str(root / "hprc-d9-bs"),
        "directional": True,
        "image": "methylgrapher:test",
    }
    for side in ("c2t", "g2a"):
        for p in files[side].values():
            Path(p).write_bytes(b"idx")
    for key in ("ref_paths", "cpg_tsv", "linear_ref_fasta", "original_gbz"):
        Path(files[key]).write_text("x\n", encoding="utf-8")
    return {
        "c2t": {k: str(v) for k, v in files["c2t"].items()},
        "g2a": {k: str(v) for k, v in files["g2a"].items()},
        "ref_paths": str(files["ref_paths"]),
        "cpg_tsv": str(files["cpg_tsv"]),
        "linear_ref_fasta": str(files["linear_ref_fasta"]),
        "original_gbz": str(files["original_gbz"]),
        "index_prefix": files["index_prefix"],
        "directional": True,
        "image": "methylgrapher:test",
        "read_level": {"enabled": True, "tile_size": 4},
        "contexts": ["CG"],
    }


def test_step_config_defaults_are_none() -> None:
    cfg = MethylGrapherWgbsStepConfig()
    assert cfg.threads is None
    assert cfg.directional is None
    assert cfg.c2t is None


def test_resolve_bundle_requires_c2t_g2a(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="missing"):
        resolve_methylgrapher_wgbs_genome(resolved_config={"ref_paths": str(tmp_path / "x")})


def test_resolve_bundle_ok_and_no_stock_fallback(tmp_path: Path) -> None:
    cfg = _touch_bundle(tmp_path)
    resolved = resolve_methylgrapher_wgbs_genome(resolved_config=cfg)
    assert resolved["c2t"]["gbz"].endswith("c2t.gbz")
    assert resolved["g2a"]["gbz"].endswith("g2a.gbz")
    bundle = resolve_wgbs_bundle_from_resolved(cfg)
    assert bundle.directional is True
    assert bundle.c2t_gbz.is_file()


def test_build_align_and_qc_bam_commands(tmp_path: Path) -> None:
    cfg = _touch_bundle(tmp_path)
    bundle = resolve_wgbs_bundle_from_resolved(cfg)
    cmd = build_align_command(
        bundle=bundle,
        work_dir=tmp_path / "work",
        fq1=tmp_path / "a_R1.fastq.gz",
        fq2=tmp_path / "a_R2.fastq.gz",
        index_prefix=str(tmp_path / "hprc-d9-bs"),
    )
    assert cmd[0].endswith("methylGrapher") or cmd[0] == "methylGrapher"
    assert "Align" in cmd
    assert "-directional" in cmd
    qc = build_qc_bam_command(
        bundle=bundle,
        fq1_c2t=tmp_path / "a.C2T.R1.fastq",
        fq2_g2a=tmp_path / "a.G2A.R2.fastq",
        threads=8,
    )
    assert qc[0] == "vg" or qc[0].endswith("vg")
    assert "giraffe" in qc
    assert qc[qc.index("-o") + 1] == "BAM"  # surjection happens inside giraffe
    assert qc[qc.index("--ref-paths") + 1] == str(bundle.ref_paths)
    assert qc[qc.index("-Z") + 1] == str(bundle.c2t_gbz)
    assert [qc[i + 1] for i, a in enumerate(qc) if a == "-f"] == [
        str(tmp_path / "a.C2T.R1.fastq"),
        str(tmp_path / "a.G2A.R2.fastq"),
    ]
    # Named coordinates are why the GAF cannot be surjected; never ask for them.
    assert "--named-coordinates" not in qc
    assert "surject" not in qc


def test_bs_conversion_rewrites_only_sequence_lines(tmp_path: Path) -> None:
    src = tmp_path / "r1.fastq"
    src.write_text(
        "@read1\nACGTCC\n+\nIIICCI\n@read2\nCCCCGG\n+\nCCIIII\n",
        encoding="utf-8",
    )
    out = tmp_path / "r1.C2T.fastq"
    _write_bs_converted_fastq(
        src, out, base_from="C", base_to="T", log_path=tmp_path / "log.txt"
    )
    assert out.read_text(encoding="utf-8") == (
        "@read1\nATGTTT\n+\nIIICCI\n@read2\nTTTTGG\n+\nCCIIII\n"
    )


def test_run_binary_stdout_redirect(tmp_path: Path) -> None:
    out = tmp_path / "blob.bin"
    log = tmp_path / "run.log"
    payload = b"\x1f\x8bBAM\x00\x01\x02"
    src = tmp_path / "src.bin"
    src.write_bytes(payload)
    _run(["cat", str(src)], log, step="bin", stdout_path=out)
    assert out.read_bytes() == payload


def test_restore_sequences_streaming_not_dict_load(tmp_path: Path) -> None:
    """Restore must merge-join with matching lex collation (incl. numeric names)."""
    import pysam

    bam_in = tmp_path / "conv.bam"
    header = {
        "HD": {"VN": "1.0", "SO": "unsorted"},
        "SQ": [{"LN": 1000, "SN": "chr1"}],
    }
    # Numeric suffixes diverge under natural (-n) vs lex (-N / unix sort):
    # natural: read9 < read10 ; lex: read10 < read9.
    with pysam.AlignmentFile(str(bam_in), "wb", header=header) as out:
        for qname, seq, flag, start in (
            ("read9", "AAAA", 99, 5),
            ("read10", "CCCC", 99, 10),
            ("read10", "GGGG", 147, 20),
            ("read9", "TTTT", 147, 30),
            ("read2", "ATAT", 99, 40),
            ("read2", "GCGC", 147, 50),
        ):
            aln = pysam.AlignedSegment()
            aln.query_name = qname
            aln.query_sequence = seq
            aln.flag = flag
            aln.reference_id = 0
            aln.reference_start = start
            aln.mapping_quality = 60
            aln.cigarstring = f"{len(seq)}M"
            aln.query_qualities = pysam.qualitystring_to_array("I" * len(seq))
            out.write(aln)

    fq1 = tmp_path / "r1.fastq"
    fq2 = tmp_path / "r2.fastq"
    fq1.write_text(
        "@read9\nACGT\n+\nIIII\n"
        "@read2\nTGCA\n+\nIIII\n"
        "@read10\nAATT\n+\nIIII\n",
        encoding="utf-8",
    )
    fq2.write_text(
        "@read10\nTTAA\n+\nIIII\n"
        "@read9\nGGCC\n+\nIIII\n"
        "@read2\nCCGG\n+\nIIII\n",
        encoding="utf-8",
    )
    out_bam = tmp_path / "restored.bam"
    log = tmp_path / "restore.log"
    _restore_original_sequences(bam_in, fq1, fq2, out_bam, log)
    assert out_bam.is_file()
    by_name = {}
    with pysam.AlignmentFile(str(out_bam), "rb") as inn:
        for aln in inn:
            by_name[(aln.query_name, aln.is_read2)] = aln.query_sequence
    assert by_name[("read2", False)] == "TGCA"
    assert by_name[("read2", True)] == "CCGG"
    assert by_name[("read9", False)] == "ACGT"
    assert by_name[("read9", True)] == "GGCC"
    assert by_name[("read10", False)] == "AATT"
    assert by_name[("read10", True)] == "TTAA"
    assert "streaming merge-join" in log.read_text(encoding="utf-8")


def test_dry_run_align_and_extract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METHYL_METHYLGRAPHER_DRY_RUN", "1")
    cfg = _touch_bundle(tmp_path / "assets")
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    (sample_dir / "S1_R1.fastq.gz").write_bytes(b"\x1f\x8b")  # tiny gzip-ish
    (sample_dir / "S1_R2.fastq.gz").write_bytes(b"\x1f\x8b")

    # resolve_paired_fastqs may need real pair naming — ensure helper accepts these.
    from methyl_worker import parabricks_runner

    monkeypatch.setattr(
        parabricks_runner,
        "resolve_paired_fastqs",
        lambda sample_path, sample_id: (
            sample_path / f"{sample_id}_R1.fastq.gz",
            sample_path / f"{sample_id}_R2.fastq.gz",
        ),
    )

    align = run_methylgrapher_wgbs_align(
        sample_id="S1",
        sample_dir=sample_dir,
        input_json={"resolvedConfig": cfg},
    )
    assert Path(align["bamPath"]).is_file()
    assert Path(align["gafPath"]).is_file()
    assert Path(align["qcMetricsTar"]).is_file()
    assert Path(align["dedupMetricsPath"]).is_file()

    extract = run_methylgrapher_wgbs_extract(
        sample_id="S1",
        sample_dir=sample_dir,
        project=str(tmp_path / "project.json"),
        input_json={"resolvedConfig": cfg, "forceRealign": True},
    )
    assert extract["n_h5_files"] >= 1
    h5 = Path(extract["h5Files"][0])
    assert h5.is_file()
    assert h5.name.endswith("-CG.h5")
    patterns = list(sample_dir.glob("*.patterns.h5"))
    assert patterns

    manifest_path = Path(extract["manifestPath"])
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["metadata"]["schema_name"] == "methylextractor.extraction_manifest"
    assert manifest["metadata"]["contexts_extracted"] == ["CG"]
    assert manifest["metadata"]["extractor"] == "methylGrapher"
    assert "cpg_weighted_mean_coverage" in manifest["summary"]
    assert manifest["summary"]["cpg_weighted_mean_coverage"] >= 10.0
    assert "1" in manifest["per_chromosome"]
    assert isinstance(manifest["per_chromosome"]["1"].get("CG"), dict)
    assert manifest["per_chromosome"]["1"]["CG"]["num_positions"] >= 1
    assert "read_filtering" not in manifest  # unavailable for graph extract; skip check
    assert manifest["tool"] == "methylGrapher"
    assert "graph_assets" in manifest

    from methyl_extraction_qc.guardrails import evaluate_guardrails
    from methyl_extraction_qc.models.config import ExtractionQCGuardrailConfig

    report = evaluate_guardrails(
        manifest,
        config=ExtractionQCGuardrailConfig(),
        expected_chromosomes=["1"],
    )
    assert report["overall_pass"] is True
    assert report["metrics"]["cpg_weighted_mean_coverage"]["pass"] is True
    assert report["metrics"]["chromosome_completeness"]["pass"] is True
    assert report["metrics"]["read_discard_fraction"]["pass"] is True


def test_force_realign_clears_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METHYL_METHYLGRAPHER_DRY_RUN", "1")
    cfg = _touch_bundle(tmp_path / "assets")
    sample_dir = tmp_path / "S2"
    sample_dir.mkdir()
    from methyl_worker import parabricks_runner

    monkeypatch.setattr(
        parabricks_runner,
        "resolve_paired_fastqs",
        lambda sample_path, sample_id: (
            sample_path / f"{sample_id}_R1.fastq.gz",
            sample_path / f"{sample_id}_R2.fastq.gz",
        ),
    )
    (sample_dir / "S2_R1.fastq.gz").write_bytes(b"x")
    (sample_dir / "S2_R2.fastq.gz").write_bytes(b"x")
    first = run_methylgrapher_wgbs_align(
        sample_id="S2", sample_dir=sample_dir, input_json={"resolvedConfig": cfg}
    )
    gaf = Path(first["gafPath"])
    stamp = gaf.read_text(encoding="utf-8")
    gaf.write_text("stale\n", encoding="utf-8")
    second = run_methylgrapher_wgbs_align(
        sample_id="S2",
        sample_dir=sample_dir,
        input_json={"resolvedConfig": cfg, "forceRealign": True},
    )
    assert Path(second["gafPath"]).read_text(encoding="utf-8") != "stale\n"
    assert stamp  # dry-run marker existed



def test_align_resolves_index_prefix_for_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config may store paths via a symlink (/work); Docker mounts use realpath."""
    assets = tmp_path / "assets"
    cfg = _touch_bundle(assets)
    link_root = tmp_path / "work_link"
    link_root.symlink_to(assets.resolve(), target_is_directory=True)
    cfg = {**cfg, "index_prefix": str(link_root / "hprc-d9-bs")}

    sample_dir = tmp_path / "S_idx"
    sample_dir.mkdir()
    (sample_dir / "S_idx_R1.fastq.gz").write_bytes(b"x")
    (sample_dir / "S_idx_R2.fastq.gz").write_bytes(b"x")
    from methyl_worker import parabricks_runner

    monkeypatch.setattr(
        parabricks_runner,
        "resolve_paired_fastqs",
        lambda sample_path, sample_id: (
            sample_path / f"{sample_id}_R1.fastq.gz",
            sample_path / f"{sample_id}_R2.fastq.gz",
        ),
    )
    captured: dict[str, str] = {}
    real_build = build_align_command

    def wrap_build(**kwargs):
        captured["index_prefix"] = kwargs["index_prefix"]
        return real_build(**kwargs)

    monkeypatch.setattr(
        "methyl_worker.methylgrapher_wgbs_runner.build_align_command",
        wrap_build,
    )
    monkeypatch.setenv("METHYL_METHYLGRAPHER_DRY_RUN", "1")

    run_methylgrapher_wgbs_align(
        sample_id="S_idx",
        sample_dir=sample_dir,
        input_json={"resolvedConfig": cfg},
    )
    assert captured["index_prefix"] == str((assets / "hprc-d9-bs").resolve())
    assert "work_link" not in captured["index_prefix"]


def test_task_models_accept_resolved_config() -> None:
    align = MethylGrapherWgbsAlignTaskInput(
        sampleId="S1",
        sampleDir="/work/samples/S1",
        resolvedConfig={"directional": True},
        forceRealign=True,
    )
    assert align.tool == "MethylGrapherWgbsAlign"
    extract = MethylGrapherWgbsExtractTaskInput(
        sampleId="S1",
        sampleDir="/work/samples/S1",
        projectPath="/work/projects/x/configs/project.json",
        resolvedConfig={"contexts": ["CG"]},
    )
    assert extract.projectPath.endswith("project.json")


def test_sample_prep_program_has_three_way_branch() -> None:
    root = Path(__file__).resolve().parents[2]
    prog = json.loads(
        (root / "workflow_engine/domain/fixtures/sample_prep.program.json").read_text()
    )
    text = json.dumps(prog)
    assert "${useWgbsPangenome}" in text
    assert "sample.methylgrapher_wgbs_align" in text
    assert "sample.methylgrapher_wgbs_extract" in text
    assert "sample.parabricks_giraffe" in text
    assert "sample.parabricks_fq2bam" in text


def test_methylcall_preflight_requires_wl_gfa(tmp_path: Path) -> None:
    cfg = _touch_bundle(tmp_path)
    bundle = resolve_wgbs_bundle_from_resolved(cfg)
    index_prefix = str(tmp_path / "hprc-d9-bs")
    with pytest.raises(RuntimeError, match="wl.gfa"):
        assert_methylcall_assets(bundle, index_prefix)
    wl = Path(f"{index_prefix}.wl.gfa")
    wl.write_text("H\tVN:Z:1.1\n", encoding="utf-8")
    nr = Path(f"{index_prefix}.wl.node.replacement.json")
    nr.write_text('{"CT":{},"GA":{}}\n', encoding="utf-8")
    assert assert_methylcall_assets(bundle, index_prefix) == wl


def test_build_methylcall_clamps_threads_and_batch_size(tmp_path: Path) -> None:
    cfg = {**_touch_bundle(tmp_path), "threads": 64, "batch_size": 8192}
    bundle = resolve_wgbs_bundle_from_resolved(cfg)
    cmd = build_methylcall_command(
        bundle=bundle, work_dir=tmp_path / "work", index_prefix=str(tmp_path / "hprc-d9-bs")
    )
    assert cmd[cmd.index("-t") + 1] == "16"
    assert cmd[cmd.index("-batch_size") + 1] == "8192"
    assert "MethylCall" in cmd


def test_mojo_engine_skips_thread_cap_and_defaults_image(tmp_path: Path) -> None:
    from methyl_worker.methylgrapher_wgbs_runner import _resolve_image

    cfg = {**_touch_bundle(tmp_path), "threads": 64, "engine": "mojo"}
    del cfg["image"]
    bundle = resolve_wgbs_bundle_from_resolved(cfg)
    assert bundle.engine == "mojo"
    cmd = build_methylcall_command(
        bundle=bundle, work_dir=tmp_path / "work", index_prefix=str(tmp_path / "hprc-d9-bs")
    )
    assert cmd[cmd.index("-t") + 1] == "64"
    assert _resolve_image(bundle) == "epimethyl/methylgrapher:1.70-mojo"


def test_step_config_accepts_engine_mojo() -> None:
    cfg = MethylGrapherWgbsStepConfig(engine="mojo")
    assert cfg.engine == "mojo"


def test_project_graph_cpg_to_linear_tsv(tmp_path: Path) -> None:
    gfa = tmp_path / "toy.wl.gfa"
    # Segment 11 starts at path offset 1000 on GRCh38 chr1.
    gfa.write_text(
        "\n".join(
            [
                "H\tVN:Z:1.1",
                "S\t11\tACGTCGGA",
                "S\t12\tTTCGAA",
                "W\tGRCh38\t0\tchr1\t1000\t1014\t>11>12",
                "",
            ]
        ),
        encoding="utf-8",
    )
    offsets = build_grch38_segment_offsets_from_gfa(gfa)
    assert offsets["11"] == ("1", 1000, 8, ">")
    assert offsets["12"] == ("1", 1008, 6, ">")

    cpg_reg = tmp_path / "cpg.tsv"
    # C0 at seg11 pos 1 (0-based; seq ACGTCGGA → CG at index 1) → 1-based genomic 1002
    cpg_reg.write_text("C0\t11\t1\t11\t2\tOther\n", encoding="utf-8")
    graph_cpg = tmp_path / "graph.cpg.tsv"
    graph_cpg.write_text("C0\t3\t10\n", encoding="utf-8")
    out = tmp_path / "linear.tsv"
    n = project_graph_cpg_to_linear_tsv(
        graph_cpg_tsv=graph_cpg,
        cpg_registry_tsv=cpg_reg,
        segment_offsets=offsets,
        out_tsv=out,
    )
    assert n == 1
    rows = out.read_text(encoding="utf-8").strip().splitlines()
    assert rows[0] == "chrom\tpos\tmC\tuC\ttnc"
    assert rows[1] == "1\t1002\t3\t7\t1"


def test_project_reverse_oriented_segment(tmp_path: Path) -> None:
    gfa = tmp_path / "toy.wl.gfa"
    # Reverse walk: segment length 4 at path start 1000 → pos0=1 maps to 1-based 1003
    # (0-based genomic = 1000 + (4-1-1) = 1002 → 1-based 1003)
    gfa.write_text(
        "\n".join(
            [
                "H\tVN:Z:1.1",
                "S\t9\tACGT",
                "W\tGRCh38\t0\tchr2\t1000\t1004\t<9",
                "",
            ]
        ),
        encoding="utf-8",
    )
    offsets = build_grch38_segment_offsets_from_gfa(gfa)
    assert offsets["9"] == ("2", 1000, 4, "<")
    cpg_reg = tmp_path / "cpg.tsv"
    cpg_reg.write_text("C0\t9\t1\t9\t2\tOther\n", encoding="utf-8")
    graph_cpg = tmp_path / "graph.cpg.tsv"
    graph_cpg.write_text("C0\t1\t4\n", encoding="utf-8")
    out = tmp_path / "linear.tsv"
    n = project_graph_cpg_to_linear_tsv(
        graph_cpg_tsv=graph_cpg,
        cpg_registry_tsv=cpg_reg,
        segment_offsets=offsets,
        out_tsv=out,
    )
    assert n == 1
    assert out.read_text(encoding="utf-8").strip().splitlines()[1] == "2\t1003\t1\t3\t1"


def test_segment_offsets_ignore_non_reference_walks(tmp_path: Path) -> None:
    gfa = tmp_path / "toy.wl.gfa"
    # Segments 21/23 are only reachable from non-GRCh38 haplotypes, and the
    # sample haplotypes visit shared segment 22 at a different offset.
    gfa.write_text(
        "\n".join(
            [
                "H\tVN:Z:1.1",
                "S\t21\tACGT",
                "S\t22\tCGCG",
                "S\t23\tTTAA",
                "W\tHG002\t1\tchr1\t500\t508\t>21>22",
                "W\tCHM13\t0\tchr1\t700\t708\t>22>23",
                "W\tGRCh38\t0\tchr1\t1000\t1004\t>22",
                "",
            ]
        ),
        encoding="utf-8",
    )
    offsets = build_grch38_segment_offsets_from_gfa(gfa)
    assert offsets == {"22": ("1", 1000, 4, ">")}


def test_catalog_registers_methylgrapher_actions() -> None:
    from methyl_worker.action_catalog import ACTION_CATALOG

    names = {e.action_name for e in ACTION_CATALOG}
    assert "sample.methylgrapher_wgbs_align" in names
    assert "sample.methylgrapher_wgbs_extract" in names
    entries = {e.action_name: e for e in ACTION_CATALOG}
    assert entries["sample.methylgrapher_wgbs_align"].action_config_key == "methylgrapher_wgbs"
    assert entries["sample.methylgrapher_wgbs_extract"].in_process_handler == (
        "_handle_methylgrapher_wgbs_extract"
    )


def test_flatten_and_package_nested_picard_metrics(tmp_path: Path) -> None:
    """Nested Parabricks outputs must all land in the flat qc-metrics tar."""
    import tarfile

    sample_id = "HBCST-NEST"
    sample_dir = tmp_path / sample_id
    metrics_dir = sample_dir / f"{sample_id}.qc-metrics"
    nested = metrics_dir / "collectmultiplemetrics"
    nested.mkdir(parents=True)
    # quality_yield already at root (old bug skipped flatten entirely in this case)
    (metrics_dir / "quality_yield.txt").write_text("TOTAL_READS\t1000\n", encoding="utf-8")
    for name in (
        "insert_size.txt",
        "gcbias_summary.txt",
        "mean_quality_by_cycle.txt",
        "sequencingArtifact.pre_adapter_summary_metrics.txt",
    ):
        (nested / name).write_text(f"{name}\tok\n", encoding="utf-8")

    _flatten_qc_metrics_dir(metrics_dir)
    for name in (
        "quality_yield.txt",
        "insert_size.txt",
        "gcbias_summary.txt",
        "mean_quality_by_cycle.txt",
        "sequencingArtifact.pre_adapter_summary_metrics.txt",
    ):
        assert (metrics_dir / name).is_file(), name

    tar_path = _package_qc_tar(sample_dir, sample_id, metrics_dir)
    with tarfile.open(tar_path, "r") as tar:
        names = set(tar.getnames())
    assert "quality_yield.txt" in names
    assert "insert_size.txt" in names
    assert "gcbias_summary.txt" in names
    assert "mean_quality_by_cycle.txt" in names
    assert "sequencingArtifact.pre_adapter_summary_metrics.txt" in names


def test_package_qc_tar_includes_nested_only_metrics(tmp_path: Path) -> None:
    """Packaging safety net: nested-only trees still enter the tar by basename."""
    import tarfile

    sample_id = "HBCST-NEST2"
    sample_dir = tmp_path / sample_id
    metrics_dir = sample_dir / f"{sample_id}.qc-metrics"
    nested = metrics_dir / "out"
    nested.mkdir(parents=True)
    (nested / "quality_yield.txt").write_text("TOTAL_READS\t1\n", encoding="utf-8")
    (nested / "insert_size.txt").write_text("MEDIAN_INSERT_SIZE\t180\n", encoding="utf-8")

    tar_path = _package_qc_tar(sample_dir, sample_id, metrics_dir)
    with tarfile.open(tar_path, "r") as tar:
        names = set(tar.getnames())
    assert names == {"quality_yield.txt", "insert_size.txt"}
