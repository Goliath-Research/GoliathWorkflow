"""Unit tests for methylGrapher WGBS pangenome SamplePrep path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_utils.action_config_resolver import resolve_methylgrapher_wgbs_genome
from methyl_worker.methylgrapher_wgbs_runner import (
    build_align_command,
    build_surject_command,
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


def test_build_align_and_surject_commands(tmp_path: Path) -> None:
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
    sur = build_surject_command(
        gaf=tmp_path / "a.gaf",
        gbz=bundle.original_gbz or bundle.c2t_gbz,
        ref_paths=bundle.ref_paths,
        out_bam=tmp_path / "out.bam",
    )
    assert sur[0] in {"vg", "vg"} or sur[0].endswith("vg")
    assert "surject" in sur


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
