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
) -> tuple[Path, dict]:
    ref = genome_fasta or path.parent / "genome.fa"
    if not ref.is_file():
        ref.write_text(">chr1\n")
    chrom_mapping = path.parent / "chrom_mapping.json"
    if not chrom_mapping.is_file():
        chrom_mapping.write_text(json.dumps({"reference": str(ref), "chromosomes": []}))

    methyl_cfg = methyl_extract if methyl_extract is not None else {
        "extract_contexts": ["CG", "CHG", "CHH"],
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
    }
    (path.parent / "samples.csv").write_text("S1\n")
    path.write_text(json.dumps(payload), encoding="utf-8")
    action_config = {
        "alignment_qc": {"genome_fasta": str(ref)},
        "methyl_extract": methyl_cfg,
    }
    return ref, action_config


def _task_input(
    sample_id: str,
    sample_dir: Path,
    ref: Path,
    action_config: dict,
    *,
    resolved_methyl_extract: dict | None = None,
) -> dict:
    methyl_cfg = resolved_methyl_extract if resolved_methyl_extract is not None else action_config["methyl_extract"]
    return {
        "sampleId": sample_id,
        "sampleDir": str(sample_dir),
        "resolvedConfig": {
            **methyl_cfg,
            "reference_fasta": str(ref),
            "genome_fasta": str(ref),
        },
    }


def test_normalize_contexts_default_all_three() -> None:
    assert runner._normalize_contexts(None) == ("CG", "CHG", "CHH")


def test_normalize_contexts_cg_only() -> None:
    assert runner._normalize_contexts(["CG"]) == ("CG",)


def test_build_command_includes_chg_chh_flags(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(project)
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    bam = sample_dir / "S1.bam"
    bam.write_bytes(b"BAM")

    cfg = runner.resolve_methyl_extract_config(project, _task_input("S1", sample_dir, ref, action_config))
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
    bam_idx = cmd.index(str(bam))
    ref_idx = cmd.index(str(ref))
    assert ref_idx == bam_idx + 1
    assert str(sample_dir) not in cmd[bam_idx + 1 : ref_idx + 1]


def test_build_command_includes_chrom_parallel_when_supported(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(
        project,
        methyl_extract={
            "extract_contexts": ["CG"],
            "threads": 10,
            "chrom_parallel": 2,
            "max_rss_gb": 32,
            "split": True,
        },
    )
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    bam = sample_dir / "S1.bam"
    bam.write_bytes(b"BAM")
    fake_bin = tmp_path / "MethylExtractor"
    fake_bin.write_text(
        "#!/bin/sh\necho 'Usage: MethylExtractor --chrom-parallel --max-rss-gb --threads'\n",
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)

    cfg = runner.resolve_methyl_extract_config(
        project,
        _task_input(
            "S1",
            sample_dir,
            ref,
            action_config,
            resolved_methyl_extract={
                **action_config["methyl_extract"],
                "extractor_bin": str(fake_bin),
            },
        ),
    )
    paths = runner.MethylExtractPaths(
        sample_dir=sample_dir,
        sample_id="S1",
        bam_path=bam,
        log_path=sample_dir / "S1.methyl_extract.log",
    )
    cmd = runner.build_methyl_extractor_command(cfg, paths)
    assert "--chrom-parallel=2" in cmd
    assert "--max-rss-gb=32" in cmd
    assert "--threads=10" in cmd


def test_build_command_cg_only_skips_chg_chh(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(
        project,
        methyl_extract={
            "extract_contexts": ["CG"],
        },
    )
    sample_dir = tmp_path / "S2"
    sample_dir.mkdir()

    cfg = runner.resolve_methyl_extract_config(
        project,
        _task_input("S2", sample_dir, ref, action_config),
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


def test_derives_chrom_mapping_from_chromosomes(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(project, chromosomes=["1", "21"])
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()

    cfg = runner.resolve_methyl_extract_config(project, _task_input("S1", sample_dir, ref, action_config))
    assert cfg.chrom_mapping.is_file()
    assert cfg.chrom_mapping.name == ".chrom_mapping.json"
    payload = json.loads(cfg.chrom_mapping.read_text(encoding="utf-8"))
    names = {row["name"] for row in payload["chromosomes"]}
    assert names == {"1", "21"}


def test_inline_chrom_mapping_object_materialized(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(project, chromosomes=["1"])
    inline = {
        "reference": str(ref),
        "chromosomes": [{"name": "1", "bam": "1", "fasta": "1", "extract": True}],
    }
    action_config["methyl_extract"] = {**action_config["methyl_extract"], "chrom_mapping": inline}
    sample_dir = tmp_path / "S2"
    sample_dir.mkdir()

    cfg = runner.resolve_methyl_extract_config(
        project,
        _task_input("S2", sample_dir, ref, action_config),
    )
    assert json.loads(cfg.chrom_mapping.read_text(encoding="utf-8")) == inline


def test_chrom_mapping_mismatch_raises(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(project, chromosomes=["1", "2"])
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    with pytest.raises(RuntimeError, match="must match project.chromosomes"):
        runner._materialize_chrom_mapping(
            sample_dir,
            {
                "reference": str(ref),
                "chromosomes": [{"name": "1", "bam": "1", "fasta": "1", "extract": True}],
            },
            ["1", "2"],
            ref,
            {},
        )


def test_ucsc_chr_contig_naming(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(
        project,
        chromosomes=["1"],
        methyl_extract={"contig_naming": "ucsc_chr", "extract_contexts": ["CG"]},
    )
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    cfg = runner.resolve_methyl_extract_config(project, _task_input("S1", sample_dir, ref, action_config))
    row = json.loads(cfg.chrom_mapping.read_text(encoding="utf-8"))["chromosomes"][0]
    assert row["bam"] == "chr1"
    assert row["name"] == "1"


def test_idempotent_skip_when_all_h5_present(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(project, chromosomes=["1"])
    sample_dir = tmp_path / "S3"
    sample_dir.mkdir()
    for name in ("1-CG.h5", "1-CHG.h5", "1-CHH.h5"):
        (sample_dir / name).write_bytes(b"h5")
    for ctx in ("CG", "CHG", "CHH"):
        (sample_dir / f"1-{ctx}.json").write_text(
            json.dumps(
                {
                    "num_positions": 100,
                    "total_methylated": 80,
                    "total_unmethylated": 20,
                    "avg_methylation_level": 0.8,
                    "avg_coverage": 12.0,
                }
            ),
            encoding="utf-8",
        )
    # Stale stub must be overwritten.
    (sample_dir / "S3.extraction_manifest.json").write_text(
        json.dumps(
            {
                "metadata": {"schema_name": "methylextractor.extraction_manifest"},
                "summary": {"cpg_weighted_mean_coverage": 20.0},
                "per_chromosome": {"21": {"CG": {"mean_coverage": 18.0}}},
            }
        ),
        encoding="utf-8",
    )

    with patch("methyl_worker.extract_runner.subprocess.run") as mock_run:
        out = runner.run_methyl_extract(
            sample_id="S3",
            sample_dir=sample_dir,
            project=project,
            input_json=_task_input("S3", sample_dir, ref, action_config),
        )

    # Skip path must not invoke MethylExtractor. Do not use assert_not_called():
    # resolve/load may call subprocess.run for unrelated probes (e.g. uname -p).
    def _is_extractor_call(call: object) -> bool:
        args = getattr(call, "args", ())
        if not args:
            return False
        cmd = args[0]
        if isinstance(cmd, (list, tuple)):
            return any("MethylExtractor" in str(part) for part in cmd)
        return "MethylExtractor" in str(cmd)

    assert not any(_is_extractor_call(c) for c in mock_run.call_args_list)
    assert out["h5Files"] == ["1-CG.h5", "1-CHG.h5", "1-CHH.h5"]
    manifest = json.loads((sample_dir / "S3.extraction_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["per_chromosome"]) == {"1"}
    assert manifest["per_chromosome"]["1"]["CG"]["mean_coverage"] == 12.0
    assert manifest["metadata"]["extractor"] == "MethylExtractor"
    assert (sample_dir / "S3.extraction_manifest.json").stat().st_size > 0


def test_build_manifest_from_stats_covers_all_chroms(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S"
    sample_dir.mkdir()
    for chrom in ("1", "2", "X"):
        (sample_dir / f"{chrom}-CG.json").write_text(
            json.dumps(
                {
                    "num_positions": 10 * int(chrom) if chrom.isdigit() else 5,
                    "total_methylated": 8,
                    "total_unmethylated": 2,
                    "avg_methylation_level": 0.8,
                    "avg_coverage": float(chrom) if chrom.isdigit() else 9.0,
                }
            ),
            encoding="utf-8",
        )
    manifest = runner.build_canonical_extraction_manifest_from_stats(
        sample_id="S",
        sample_dir=sample_dir,
        chromosomes=["1", "2", "X"],
        contexts=["CG"],
        h5_files=["1-CG.h5", "2-CG.h5", "X-CG.h5"],
    )
    assert set(manifest["per_chromosome"]) == {"1", "2", "X"}
    assert manifest["summary"]["n_chromosomes"] == 3
    assert manifest["summary"]["cpg_weighted_mean_coverage"] > 0


def test_resolve_bam_legacy_name(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S4"
    sample_dir.mkdir()
    legacy = sample_dir / "S4.clara_parabrics.duplicates_marked.bam"
    legacy.write_bytes(b"BAM")
    assert runner.resolve_bam_path(sample_dir, "S4") == legacy


def test_run_invokes_methyl_extractor(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    ref, action_config = _write_min_project(project, chromosomes=["1"])
    sample_dir = tmp_path / "S5"
    sample_dir.mkdir()
    (sample_dir / "S5.bam").write_bytes(b"BAM")

    def fake_run(cmd, **kwargs):
        for name in ("1-CG.h5", "1-CHG.h5", "1-CHH.h5"):
            (sample_dir / name).write_bytes(b"h5")
        for ctx in ("CG", "CHG", "CHH"):
            (sample_dir / f"1-{ctx}.json").write_text(
                json.dumps(
                    {
                        "num_positions": 50,
                        "total_methylated": 40,
                        "total_unmethylated": 10,
                        "avg_methylation_level": 0.8,
                        "avg_coverage": 11.0,
                    }
                ),
                encoding="utf-8",
            )
        return type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    with patch.object(runner, "_extractor_bin", return_value="/usr/bin/MethylExtractor"):
        with patch("methyl_worker.extract_runner.subprocess.run", side_effect=fake_run):
            out = runner.run_methyl_extract(
                sample_id="S5",
                sample_dir=sample_dir,
                project=project,
                input_json=_task_input("S5", sample_dir, ref, action_config),
            )

    assert len(out["h5Files"]) == 3
    manifest = json.loads((sample_dir / "S5.extraction_manifest.json").read_text(encoding="utf-8"))
    assert manifest["per_chromosome"]["1"]["CG"]["mean_coverage"] == 11.0
    assert out["extractionManifest"].endswith("S5.extraction_manifest.json")
