"""Tests for Parabricks fq2bam_meth Docker runner."""

from __future__ import annotations

import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from methyl_worker import parabricks_runner as runner


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

    mock_run.assert_not_called()
    assert out["bamPath"] == str(sample_dir / "S5.bam")
    assert out["qcMetricsTar"] == str(sample_dir / "S5.qc-metrics.tar")


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
        with patch("methyl_worker.parabricks_runner.subprocess.run", side_effect=fake_run):
            out = runner.run_fq2bam_meth(
                sample_id="S7",
                sample_dir=sample_dir,
                reference_fasta=ref,
            )

    assert out["bamPath"] == str(sample_dir / "S7.bam")
    assert out["qcMetricsTar"] == str(sample_dir / "S7.qc-metrics.tar")


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
