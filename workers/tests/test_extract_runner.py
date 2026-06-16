"""Tests for MethylExtractor extract_runner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from methyl_worker import extract_runner as runner


def _write_min_project(
    path: Path,
    *,
    chromosomes: list[str] | None = None,
    methyl_extract: dict | None = None,
    genome_fasta: Path | None = None,
) -> Path:
    ref = genome_fasta or path.parent / "genome.fa"
    if not ref.is_file():
        ref.write_text(">chr1\n")
    chrom_mapping = path.parent / "chrom_mapping.json"
    if not chrom_mapping.is_file():
        chrom_mapping.write_text(json.dumps({"reference": str(ref), "chromosomes": []}))

    step_config: dict = {
        "alignment_qc": {"genome_fasta": str(ref)},
    }
    if methyl_extract is not None:
        step_config["methyl_extract"] = methyl_extract
    else:
        step_config["methyl_extract"] = {
            "extract_contexts": ["CG", "CHG", "CHH"],
            "chrom_mapping": str(chrom_mapping),
            "threads": 10,
            "min_mapq": 20,
            "split": True,
        }

    payload = {
        "project_name": "test",
        "output_base": str(path.parent / "out"),
        "chromosomes": chromosomes or ["1", "2"],
        "contexts": ["CG"],
        "group1": {"label": "g1", "sample_paths": [str(path.parent / "samples.csv")]},
        "group2": {"label": "g2", "sample_paths": [str(path.parent / "samples.csv")]},
        "step_config": step_config,
    }
    (path.parent / "samples.csv").write_text("S1\n")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return ref


def test_normalize_contexts_default_all_three() -> None:
    assert runner._normalize_contexts(None) == ("CG", "CHG", "CHH")


def test_normalize_contexts_cg_only() -> None:
    assert runner._normalize_contexts(["CG"]) == ("CG",)


def test_build_command_includes_chg_chh_flags(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref = _write_min_project(project)
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    bam = sample_dir / "S1.bam"
    bam.write_bytes(b"BAM")

    cfg = runner.resolve_methyl_extract_config(
        project,
        {
            "sampleId": "S1",
            "sampleDir": str(sample_dir),
            "referenceFasta": str(ref),
        },
    )
    paths = runner.MethylExtractPaths(
        sample_dir=sample_dir,
        sample_id="S1",
        bam_path=bam,
        log_path=sample_dir / "S1.methyl_extract.log",
    )

    with patch.object(runner, "_extractor_bin", return_value="/usr/bin/MethylExtractor"):
        cmd = runner.build_methyl_extractor_command(cfg, paths)

    assert "--CHG" in cmd
    assert "--CHH" in cmd
    assert "--split" in cmd
    assert f"--min-mapq=20" in cmd
    assert f"--threads=10" in cmd
    assert str(bam) in cmd
    assert str(ref) in cmd


def test_build_command_cg_only_skips_chg_chh(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref = _write_min_project(
        project,
        methyl_extract={
            "extract_contexts": ["CG"],
            "chrom_mapping": str(project.parent / "chrom_mapping.json"),
        },
    )
    sample_dir = tmp_path / "S2"
    sample_dir.mkdir()

    cfg = runner.resolve_methyl_extract_config(
        project,
        {"sampleId": "S2", "sampleDir": str(sample_dir), "referenceFasta": str(ref)},
    )
    paths = runner.MethylExtractPaths(
        sample_dir=sample_dir,
        sample_id="S2",
        bam_path=sample_dir / "S2.bam",
        log_path=sample_dir / "S2.methyl_extract.log",
    )

    with patch.object(runner, "_extractor_bin", return_value="/usr/bin/MethylExtractor"):
        cmd = runner.build_methyl_extractor_command(cfg, paths)

    assert "--CHG" not in cmd
    assert "--CHH" not in cmd


def test_missing_chrom_mapping_raises(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref = _write_min_project(
        project,
        methyl_extract={"extract_contexts": ["CG"]},
    )
    with pytest.raises(RuntimeError, match="chrom_mapping"):
        runner.resolve_methyl_extract_config(
            project,
            {"sampleId": "S1", "sampleDir": str(tmp_path / "S1"), "referenceFasta": str(ref)},
        )


def test_idempotent_skip_when_all_h5_present(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref = _write_min_project(project, chromosomes=["1"])
    sample_dir = tmp_path / "S3"
    sample_dir.mkdir()
    for name in ("1-CG.h5", "1-CHG.h5", "1-CHH.h5"):
        (sample_dir / name).write_bytes(b"h5")

    with patch("methyl_worker.extract_runner.subprocess.run") as mock_run:
        out = runner.run_methyl_extract(
            sample_id="S3",
            sample_dir=sample_dir,
            project=project,
            input_json={"referenceFasta": str(ref)},
        )

    mock_run.assert_not_called()
    assert out["h5Files"] == ["1-CG.h5", "1-CHG.h5", "1-CHH.h5"]


def test_resolve_bam_legacy_name(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S4"
    sample_dir.mkdir()
    legacy = sample_dir / "S4.clara_parabrics.duplicates_marked.bam"
    legacy.write_bytes(b"BAM")
    assert runner.resolve_bam_path(sample_dir, "S4") == legacy


def test_run_invokes_methyl_extractor(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref = _write_min_project(project, chromosomes=["1"])
    sample_dir = tmp_path / "S5"
    sample_dir.mkdir()
    (sample_dir / "S5.bam").write_bytes(b"BAM")

    def fake_run(cmd, **kwargs):
        for name in ("1-CG.h5", "1-CHG.h5", "1-CHH.h5"):
            (sample_dir / name).write_bytes(b"h5")
        return type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    with patch.object(runner, "_extractor_bin", return_value="/usr/bin/MethylExtractor"):
        with patch("methyl_worker.extract_runner.subprocess.run", side_effect=fake_run):
            out = runner.run_methyl_extract(
                sample_id="S5",
                sample_dir=sample_dir,
                project=project,
                input_json={"referenceFasta": str(ref)},
            )

    assert len(out["h5Files"]) == 3
