"""Tests for MethylExtractor read_level wiring."""

from __future__ import annotations

from methyl_worker.extract_runner import (
    MethylExtractConfig,
    _resolve_read_level,
    build_methyl_extractor_command,
    expected_pattern_h5_files,
)


def test_resolve_read_level_dict():
    enabled, tile = _resolve_read_level({"read_level": {"enabled": True, "tile_size": 6}})
    assert enabled is True
    assert tile == 6


def test_build_command_includes_read_level_flags(tmp_path):
    fake_bin = tmp_path / "MethylExtractor.exe"
    fake_bin.write_text("", encoding="utf-8")
    cfg = MethylExtractConfig(
        sample_id="s1",
        sample_dir=tmp_path,
        project_path=tmp_path / "p.json",
        chromosomes=("1",),
        extract_contexts=("CG",),
        reference_fasta=tmp_path / "ref.fa",
        chrom_mapping=tmp_path / "map.json",
        extractor_bin=str(fake_bin),
        threads=None,
        min_mapq=None,
        min_phred=None,
        min_cov=None,
        cap_cov=None,
        compression=None,
        chunk_size=None,
        output_format="hdf5",
        split=True,
        read_level=True,
        tile_size=4,
    )
    from methyl_worker.extract_runner import MethylExtractPaths

    paths = MethylExtractPaths(
        sample_dir=tmp_path,
        sample_id="s1",
        bam_path=tmp_path / "s1.bam",
        log_path=tmp_path / "s1.log",
    )
    cmd = build_methyl_extractor_command(cfg, paths)
    assert "--read-level" in cmd
    assert "--tile-size=4" in cmd


def test_expected_pattern_files():
    assert expected_pattern_h5_files(["1", "2"], ["CG"]) == [
        "1-CG.patterns.h5",
        "2-CG.patterns.h5",
    ]
