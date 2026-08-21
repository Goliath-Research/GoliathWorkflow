"""Tests for Parabricks fq2bam_meth Docker runner."""

from __future__ import annotations

import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from methyl_worker import parabricks_runner as runner


def test_resolve_paired_fastqs_prefers_trimmed_outputs(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_trim"
    sample_dir.mkdir()
    (sample_dir / "S_trim_1.fastq.gz").write_bytes(b"raw1")
    (sample_dir / "S_trim_2.fastq.gz").write_bytes(b"raw2")
    (sample_dir / "S_trim_1.trimmed.fastq.gz").write_bytes(b"t1")
    (sample_dir / "S_trim_2.trimmed.fastq.gz").write_bytes(b"t2")

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S_trim")
    assert [p.name for p in fastqs] == [
        "S_trim_1.trimmed.fastq.gz",
        "S_trim_2.trimmed.fastq.gz",
    ]
    source = runner.resolve_paired_fastqs(sample_dir, "S_trim", prefer_trimmed=False)
    assert [p.name for p in source] == ["S_trim_1.fastq.gz", "S_trim_2.fastq.gz"]


def test_resolve_paired_fastqs_prefers_explicit_names(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    (sample_dir / "S1_1.fastq.gz").write_bytes(b"r1")
    (sample_dir / "S1_2.fastq.gz").write_bytes(b"r2")
    (sample_dir / "other_1.fastq.gz").write_bytes(b"x")

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S1")
    assert [p.name for p in fastqs] == ["S1_1.fastq.gz", "S1_2.fastq.gz"]


def test_resolve_paired_fastqs_recursive_glob(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S2"
    lane = sample_dir / "lane1"
    lane.mkdir(parents=True)
    (lane / "R1.fastq.gz").write_bytes(b"r1")
    (lane / "R2.fastq.gz").write_bytes(b"r2")

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S2")
    assert len(fastqs) == 2


def test_resolve_paired_fastqs_wrong_count(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S3"
    sample_dir.mkdir()
    (sample_dir / "only.fastq.gz").write_bytes(b"r1")

    with pytest.raises(RuntimeError, match="found 1"):
        runner.resolve_paired_fastqs(sample_dir, "S3")


def test_resolve_paired_fastqs_even_unparsed_names(tmp_path: Path) -> None:
    """Clara --in-fq accepts even unparsed FASTQs as sequential R1/R2 pairs."""
    sample_dir = tmp_path / "S_even"
    sample_dir.mkdir()
    (sample_dir / "flowcellA.fastq.gz").write_bytes(b"r1")
    (sample_dir / "flowcellB.fastq.gz").write_bytes(b"r2")

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S_even")
    assert [p.name for p in fastqs] == ["flowcellA.fastq.gz", "flowcellB.fastq.gz"]


def test_resolve_paired_fastqs_two_r1s_do_not_pair(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_two_r1"
    sample_dir.mkdir()
    (sample_dir / "laneA_1.fastq.gz").write_bytes(b"a")
    (sample_dir / "laneB_1.fastq.gz").write_bytes(b"b")

    with pytest.raises(RuntimeError, match="Incomplete FASTQ mate group"):
        runner.resolve_paired_fastqs(sample_dir, "S_two_r1")


def test_resolve_paired_fastqs_r1_plus_unparsed_does_not_pair(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_mix"
    sample_dir.mkdir()
    (sample_dir / "sample_R1.fastq.gz").write_bytes(b"r1")
    (sample_dir / "orphan.fastq.gz").write_bytes(b"x")

    with pytest.raises(RuntimeError, match="Incomplete FASTQ mate group"):
        runner.resolve_paired_fastqs(sample_dir, "S_mix")


def test_resolve_paired_fastqs_restores_from_download_caas(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_caas"
    sample_dir.mkdir()
    key = sample_dir / ".caas" / "sample_download_fastq" / "abc123"
    key.mkdir(parents=True)
    (key / "S_caas_1.fastq.gz").write_bytes(b"r1")
    (key / "S_caas_2.fastq.gz").write_bytes(b"r2")
    (key / "manifest.json").write_text(
        '{"schema_version":"1.2","action_name":"sample.download_fastq",'
        '"result_code":0,"artifacts":[],"task_output":{"fastqFiles":[]}}',
        encoding="utf-8",
    )

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S_caas")
    assert len(fastqs) == 2
    assert all(p.is_file() for p in fastqs)
    assert {p.name for p in fastqs} == {"S_caas_1.fastq.gz", "S_caas_2.fastq.gz"}
    assert all(".caas" not in p.parts for p in fastqs)


def test_resolve_paired_fastqs_multiple_lane_pairs(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_lanes"
    lane_a = sample_dir / "AN000_flowcellA"
    lane_b = sample_dir / "AN000_flowcellB"
    lane_a.mkdir(parents=True)
    lane_b.mkdir(parents=True)
    (lane_a / "S_lanes_1.fastq.gz").write_bytes(b"a1")
    (lane_a / "S_lanes_2.fastq.gz").write_bytes(b"a2")
    (lane_b / "S_lanes_1.fastq.gz").write_bytes(b"b1")
    (lane_b / "S_lanes_2.fastq.gz").write_bytes(b"b2")

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S_lanes")
    assert len(fastqs) == 4
    assert [p.name for p in fastqs] == [
        "S_lanes_1.fastq.gz",
        "S_lanes_2.fastq.gz",
        "S_lanes_1.fastq.gz",
        "S_lanes_2.fastq.gz",
    ]
    assert {p.parent.name for p in fastqs} == {"AN000_flowcellA", "AN000_flowcellB"}


def test_resolve_paired_fastqs_r_separator_distinct_from_bare_underscore(
    tmp_path: Path,
) -> None:
    sample_dir = tmp_path / "S_sep"
    sample_dir.mkdir()
    (sample_dir / "sample_1.fastq.gz").write_bytes(b"u1")
    (sample_dir / "sample_2.fastq.gz").write_bytes(b"u2")
    (sample_dir / "sample_R1.fastq.gz").write_bytes(b"r1")
    (sample_dir / "sample_R2.fastq.gz").write_bytes(b"r2")

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S_sep")
    assert [p.name for p in fastqs] == [
        "sample_1.fastq.gz",
        "sample_2.fastq.gz",
        "sample_R1.fastq.gz",
        "sample_R2.fastq.gz",
    ]


def test_resolve_paired_fastqs_illumina_segments_are_distinct_pairs(
    tmp_path: Path,
) -> None:
    sample_dir = tmp_path / "S_seg"
    sample_dir.mkdir()
    (sample_dir / "sample_R1_001.fastq.gz").write_bytes(b"a1")
    (sample_dir / "sample_R2_001.fastq.gz").write_bytes(b"a2")
    (sample_dir / "sample_R1_002.fastq.gz").write_bytes(b"b1")
    (sample_dir / "sample_R2_002.fastq.gz").write_bytes(b"b2")

    fastqs = runner.resolve_paired_fastqs(sample_dir, "S_seg")
    assert [p.name for p in fastqs] == [
        "sample_R1_001.fastq.gz",
        "sample_R2_001.fastq.gz",
        "sample_R1_002.fastq.gz",
        "sample_R2_002.fastq.gz",
    ]


def test_resolve_paired_fastqs_duplicate_mate_raises(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_dup"
    sample_dir.mkdir()
    (sample_dir / "sample_1.fastq.gz").write_bytes(b"gz")
    (sample_dir / "sample_1.fastq").write_bytes(b"plain")
    (sample_dir / "sample_2.fastq.gz").write_bytes(b"r2")

    with pytest.raises(RuntimeError, match="Duplicate FASTQ mate 1"):
        runner.resolve_paired_fastqs(sample_dir, "S_dup")


def test_build_docker_command_multiple_in_fq_pairs(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_multi"
    lane_a = sample_dir / "laneA"
    lane_b = sample_dir / "laneB"
    lane_a.mkdir(parents=True)
    lane_b.mkdir(parents=True)
    ref = tmp_path / "genomes" / "genome.fa"
    ref.parent.mkdir(parents=True)
    ref.write_text(">ref\n")
    fqs = [
        lane_a / "S_multi_1.fastq.gz",
        lane_a / "S_multi_2.fastq.gz",
        lane_b / "S_multi_1.fastq.gz",
        lane_b / "S_multi_2.fastq.gz",
    ]
    for path in fqs:
        path.write_bytes(b"x")

    cfg = runner.ParabricksConfig(
        image="nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1",
        gpu_flags=("--gpus", "all"),
        bwa_threads=8,
        extra_docker_args=(),
        cleanup_tmp=True,
        engine="parabricks",
        align_device="auto",
    )
    paths = runner._resolve_paths(sample_dir, "S_multi", ref)
    with patch.object(runner, "_docker_bin", return_value="/usr/bin/docker"):
        cmd = runner._build_docker_command(cfg, paths, fqs)

    assert cmd.count("--in-fq") == 2
    first = cmd.index("--in-fq")
    second = cmd.index("--in-fq", first + 1)
    assert cmd[first + 1] == "/workdir/laneA/S_multi_1.fastq.gz"
    assert cmd[first + 2] == "/workdir/laneA/S_multi_2.fastq.gz"
    assert cmd[second + 1] == "/workdir/laneB/S_multi_1.fastq.gz"
    assert cmd[second + 2] == "/workdir/laneB/S_multi_2.fastq.gz"


def test_build_docker_command_mounts_and_flags(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S4"
    sample_dir.mkdir()
    ref = tmp_path / "genomes" / "genome.fa"
    ref.parent.mkdir(parents=True)
    ref.write_text(">ref\n")

    cfg = runner.ParabricksConfig(
        image="nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
        gpu_flags=("--gpus", "all"),
        bwa_threads=8,
        extra_docker_args=(),
        cleanup_tmp=True,
        engine="parabricks",
        align_device="auto",
    )
    paths = runner._resolve_paths(sample_dir, "S4", ref)
    fq1 = sample_dir / "S4_1.fastq.gz"
    fq2 = sample_dir / "S4_2.fastq.gz"
    fq1.write_bytes(b"1")
    fq2.write_bytes(b"2")

    with patch.object(runner, "_docker_bin", return_value="/usr/bin/docker"):
        cmd = runner._build_docker_command(cfg, paths, [fq1, fq2])

    joined = " ".join(cmd)
    assert "/usr/bin/docker run --rm --gpus all" in joined
    assert f"{sample_dir.resolve()}:/workdir" in cmd
    assert f"{ref.parent.resolve()}:/genomes:ro" in cmd
    assert cmd[cmd.index(cfg.image) - 2 : cmd.index(cfg.image)] == ["--entrypoint", "sh"]
    assert "umask 000" in " ".join(cmd)
    assert "pbrun" in cmd
    assert "fq2bam_meth" in cmd
    assert "--in-fq" in cmd
    idx = cmd.index("--in-fq")
    assert cmd[idx + 1] == "/workdir/S4_1.fastq.gz"
    assert cmd[idx + 2] == "/workdir/S4_2.fastq.gz"
    assert "--out-bam=/outputdir/S4.bam" in cmd
    assert "--out-qc-metrics-dir=/outputdir/S4.qc-metrics" in cmd
    assert "--bwa-cpu-thread-pool=8" in cmd
    assert "--gpusort" in cmd
    assert "--gpuwrite" in cmd


def test_idempotent_skip_when_bam_and_qc_tar_exist(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S5"
    sample_dir.mkdir()
    ref = tmp_path / "genome.fa"
    ref.write_text(">ref\n")
    (sample_dir / "S5.bam").write_bytes(b"BAM")
    (sample_dir / "S5.qc-metrics.tar").write_bytes(b"TAR")

    with patch.dict(
        "os.environ",
        {"METHYL_PARABRICKS_IMAGE": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"},
    ):
        with patch("methyl_worker.parabricks_runner.subprocess.run") as mock_run:
            out = runner.run_fq2bam_meth(
                sample_id="S5",
                sample_dir=sample_dir,
                reference_fasta=ref,
            )

    docker_calls = [
        c
        for c in mock_run.call_args_list
        if c.args and any("docker" in str(x) or "pbrun" in str(x) for x in c.args[0])
    ]
    assert not docker_calls
    assert out["bamPath"] == str(sample_dir / "S5.bam")
    assert out["qcMetricsTar"] == str(sample_dir / "S5.qc-metrics.tar")


def test_reset_tmp_clears_leftover_children(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_tmp"
    sample_dir.mkdir()
    ref = tmp_path / "genome.fa"
    ref.write_text(">ref\n")
    paths = runner._resolve_paths(sample_dir, "S_tmp", ref)
    leftover = paths.tmp_dir / "ALLU26WX"
    leftover.mkdir(parents=True)
    (leftover / "stale").write_text("x")

    runner._reset_tmp(paths)

    assert paths.tmp_dir.is_dir()
    assert not leftover.exists()
    assert list(paths.tmp_dir.iterdir()) == []


def test_package_qc_metrics_dir_to_tar(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S6"
    sample_dir.mkdir()
    ref = tmp_path / "genome.fa"
    ref.write_text(">ref\n")
    paths = runner._resolve_paths(sample_dir, "S6", ref)
    paths.qc_metrics_dir.mkdir()
    (paths.qc_metrics_dir / "metrics.txt").write_text("ok")

    tar_path = runner._package_qc_metrics(paths)
    assert tar_path is not None
    assert tar_path.is_file()

    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
    assert any(name.endswith("metrics.txt") for name in names)


def test_run_fq2bam_meth_invokes_docker(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S7"
    sample_dir.mkdir()
    ref = tmp_path / "genome.fa"
    ref.write_text(">ref\n")
    (sample_dir / "S7_1.fastq.gz").write_bytes(b"1")
    (sample_dir / "S7_2.fastq.gz").write_bytes(b"2")

    def fake_run(cmd, **kwargs):
        bam = sample_dir / "S7.bam"
        qc_dir = sample_dir / "S7.qc-metrics"
        qc_dir.mkdir()
        (qc_dir / "summary.txt").write_text("qc")
        bam.write_bytes(b"BAM")
        return type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    with patch.dict(
        "os.environ",
        {"METHYL_PARABRICKS_IMAGE": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"},
    ):
        with patch("methyl_worker.capabilities._gpu_available", return_value=True):
            with patch("methyl_worker.parabricks_runner.subprocess.run", side_effect=fake_run):
                out = runner.run_fq2bam_meth(
                    sample_id="S7",
                    sample_dir=sample_dir,
                    reference_fasta=ref,
                )

    assert out["bamPath"] == str(sample_dir / "S7.bam")
    assert out["qcMetricsTar"] == str(sample_dir / "S7.qc-metrics.tar")


def test_build_mojo_fq2bam_docker_command(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S8"
    sample_dir.mkdir()
    ref = tmp_path / "genomes" / "genome.fa"
    ref.parent.mkdir(parents=True)
    ref.write_text(">ref\n")
    cfg = runner.ParabricksConfig(
        image="epimethyl/methylgrapher:1.70-mojo-rocm",
        gpu_flags=("--device=/dev/kfd",),
        bwa_threads=8,
        extra_docker_args=(),
        cleanup_tmp=True,
        engine="mojo",
        align_device="amd",
    )
    paths = runner._resolve_paths(sample_dir, "S8", ref)
    fq1 = sample_dir / "S8_1.fastq.gz"
    fq2 = sample_dir / "S8_2.fastq.gz"
    fq1.write_bytes(b"1")
    fq2.write_bytes(b"2")

    with patch.object(runner, "_docker_bin", return_value="/usr/bin/docker"):
        cmd = runner._build_docker_command(cfg, paths, [fq1, fq2])

    assert "MojoFq2bamMeth" in cmd
    assert "pbrun" not in cmd
    assert "-device" in cmd
    assert "amd" in cmd
    assert cfg.image in cmd
    assert "--entrypoint" in cmd
    assert "umask 000" in " ".join(cmd)


def test_resolve_mojo_engine_defaults_image(tmp_path: Path) -> None:
    cfg = runner.resolve_parabricks_config(
        input_json={"resolvedConfig": {"engine": "mojo", "align_device": "auto", "bwa_threads": 4}}
    )
    assert cfg.engine == "mojo"
    assert cfg.align_device == "auto"
    assert "methylgrapher" in cfg.image
    assert cfg.bwa_threads == 4


def test_collectmultiplemetrics_ignores_mojo_methylgrapher_resolved_config() -> None:
    """WGBS Mojo align resolvedConfig must not put pbrun in the Mojo image."""
    clara = "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
    with patch.dict(
        "os.environ",
        {"METHYL_PARABRICKS_IMAGE": clara, "METHYL_PARABRICKS_GPU_FLAGS": "--gpus all"},
        clear=False,
    ):
        cfg = runner.resolve_collectmultiplemetrics_config(
            input_json={
                "resolvedConfig": {
                    "engine": "mojo",
                    "image": "epimethyl/methylgrapher:1.70-mojo",
                    "align_engine": "gpu_giraffe",
                }
            }
        )
    assert cfg.engine == "parabricks"
    assert cfg.image == clara
    assert "methylgrapher" not in cfg.image


def test_resolve_mojo_cpu_has_no_gpu_flags(tmp_path: Path) -> None:
    """align_device=cpu must not inject --gpus all (breaks hosts without NVIDIA CTK)."""
    with patch.dict(
        "os.environ",
        {"METHYL_PARABRICKS_GPU_FLAGS": "--gpus all", "METHYL_MOJO_GPU_FLAGS": ""},
        clear=False,
    ):
        # Explicit empty METHYL_MOJO_GPU_FLAGS wins for cpu; Clara env must not apply.
        cfg = runner.resolve_parabricks_config(
            input_json={"resolvedConfig": {"engine": "mojo", "align_device": "cpu"}}
        )
    assert cfg.engine == "mojo"
    assert cfg.align_device == "cpu"
    assert cfg.gpu_flags == ()

    with patch.dict(
        "os.environ",
        {"METHYL_PARABRICKS_GPU_FLAGS": "--gpus all"},
        clear=False,
    ):
        # When METHYL_MOJO_GPU_FLAGS unset, cpu default is still empty (not --gpus all).
        import os

        os.environ.pop("METHYL_MOJO_GPU_FLAGS", None)
        cfg2 = runner.resolve_parabricks_config(
            input_json={"resolvedConfig": {"engine": "mojo", "align_device": "cpu"}}
        )
    assert cfg2.gpu_flags == ()


def test_resolve_parabricks_from_project_action_config(tmp_path: Path) -> None:
    import json

    project = tmp_path / "project.json"
    project.write_text(
        json.dumps(
            {
                "project_name": "test",
                "output_base": str(tmp_path / "out"),
                "chromosomes": ["1"],
                "contexts": ["CG"],
                "group1": {"label": "g1", "sample_paths": [str(tmp_path / "s.csv")]},
                "group2": {"label": "g2", "sample_paths": [str(tmp_path / "s.csv")]},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "s.csv").write_text("S1\n")

    cfg = runner.resolve_parabricks_config(
        project_path=project,
        input_json={
            "actionConfig": {
                "parabricks": {
                    "image": "custom/parabricks:1.0",
                    "bwa_threads": 4,
                }
            }
        },
    )
    assert cfg.image == "custom/parabricks:1.0"
    assert cfg.bwa_threads == 4
