"""
Tests for the CIS-BP TF-motif integration (mode 1A) and its pluggable framework.

All tests run fully offline: network download and the real genome are never
touched. A tiny synthetic CIS-BP bundle + FASTA + GTF exercise the promoter-scan
path, and a prebuilt GMT exercises the ORA + merge wiring.
"""

import numpy as np
import pandas as pd
import pytest
from contextlib import contextmanager

from methyl_enricher.config import CisbpConfig, EnricherStepConfig
from methyl_enricher.cisbp import download as download_mod
from methyl_enricher.cisbp import pwm as pwm_mod
from methyl_enricher.cisbp import gene_sets, registry, run_cisbp, CisbpContext, available_modes
from methyl_enricher.cisbp.download import resolve_bundle
from methyl_enricher.enricher_completeness import merge_library_results
from methyl_enricher.module_pipeline import _library_category


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def test_config_nested_and_flat():
    nested = EnricherStepConfig.model_validate(
        {"cisbp": {"enabled": True, "mode": "gene_sets", "species": "Homo_sapiens"}}
    )
    assert nested.cisbp.enabled is True
    assert nested.cisbp.mode == "gene_sets"
    assert nested.cisbp.gene_set_source == "promoter_scan"  # default

    flat = EnricherStepConfig.model_validate({"cisbp_enabled": True, "cisbp_mode": "annotate"})
    assert flat.cisbp_enabled is True
    assert flat.cisbp_mode == "annotate"


def test_cisbp_categorized_as_tf():
    assert _library_category("CIS-BP") == "tf"


# --------------------------------------------------------------------------- #
# Registry / planned modes
# --------------------------------------------------------------------------- #
def test_registry_modes_and_stubs():
    assert set(available_modes()) == {"gene_sets", "annotate", "motif_scan"}
    assert callable(registry.get_mode_handler("gene_sets"))
    with pytest.raises(ValueError):
        registry.get_mode_handler("nope")

    for planned in ("annotate", "motif_scan"):
        cfg = CisbpConfig(enabled=True, mode=planned)
        with pytest.raises(NotImplementedError):
            run_cisbp(cfg, ["GENEA"], "/tmp/does-not-matter", CisbpContext())


def test_disabled_returns_none(tmp_path):
    assert run_cisbp(CisbpConfig(enabled=False), ["A"], tmp_path, CisbpContext()) is None
    assert run_cisbp(None, ["A"], tmp_path, CisbpContext()) is None


# --------------------------------------------------------------------------- #
# PWM parsing + scanning
# --------------------------------------------------------------------------- #
def _write_acgt_pwm(path):
    """Write a PWM that strongly prefers the literal motif ACGT."""
    lines = ["Pos\tA\tC\tG\tT"]
    prefs = [(0,), (1,), (2,), (3,)]  # A, C, G, T
    for i, (pref,) in enumerate(prefs, start=1):
        probs = [0.01, 0.01, 0.01, 0.01]
        probs[pref] = 0.97
        lines.append(f"{i}\t" + "\t".join(str(p) for p in probs))
    path.write_text("\n".join(lines) + "\n")


def test_pwm_load_and_scan(tmp_path):
    pwm_path = tmp_path / "M0001.txt"
    _write_acgt_pwm(pwm_path)
    mat = pwm_mod.load_pwm(pwm_path)
    assert mat is not None and mat.shape == (4, 4)
    log_odds = pwm_mod.to_log_odds(mat)

    assert pwm_mod.sequence_has_hit(log_odds, "TTTTACGTTTTT", threshold=0.85)
    assert not pwm_mod.sequence_has_hit(log_odds, "AAAAAAAAAAAA", threshold=0.85)

    # Empty (header-only) PWM -> None
    empty = tmp_path / "empty.txt"
    empty.write_text("Pos\tA\tC\tG\tT\n")
    assert pwm_mod.load_pwm(empty) is None


# --------------------------------------------------------------------------- #
# Prebuilt GMT -> ORA -> merge
# --------------------------------------------------------------------------- #
def test_prebuilt_gmt_ora_and_merge(tmp_path):
    gmt_path = tmp_path / "tf_targets.gmt"
    gmt = {
        "TF_HIT": ["GENEA", "GENEB", "GENEC", "GENED"],
        "TF_MISS": ["ZZZ1", "ZZZ2", "ZZZ3", "ZZZ4"],
    }
    gene_sets.write_gmt(gmt, gmt_path)

    cfg = CisbpConfig(enabled=True, mode="gene_sets", gene_set_source="prebuilt_gmt",
                      gmt_path=str(gmt_path), label="CIS-BP")
    genes = ["GENEA", "GENEB", "GENEC", "GENED", "OTHER1", "OTHER2"]
    out = tmp_path / "out"
    label = run_cisbp(cfg, genes, out, CisbpContext(cache_dir=tmp_path / "cache"))
    assert label == "CIS-BP"

    csv = out / "enrich_CIS-BP.csv"
    assert csv.is_file()
    df = pd.read_csv(csv)
    for col in ("Term", "Adjusted P-value", "Genes", "library"):
        assert col in df.columns
    assert (df["library"] == "CIS-BP").all()
    assert "TF_HIT" in set(df["Term"])

    merged = merge_library_results(out, ["CIS-BP"], cutoff=0.05)
    assert not merged.empty
    assert "TF_HIT" in set(merged["Term"])


def test_load_gmt_preserves_first_gene_when_description_is_empty(tmp_path):
    gmt_path = tmp_path / "empty_desc.gmt"
    gmt_path.write_text(
        "TF_EMPTY_DESC\t\tGENE_A\tGENE_B\tGENE_C\n",
        encoding="utf-8",
    )
    parsed = gene_sets.load_gmt(gmt_path)
    assert parsed["TF_EMPTY_DESC"] == ["GENE_A", "GENE_B", "GENE_C"]


# --------------------------------------------------------------------------- #
# Offline promoter-scan GMT build (synthetic bundle + FASTA + GTF)
# --------------------------------------------------------------------------- #
def _make_synthetic_bundle(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "TF_Information.txt").write_text(
        "Motif_ID\tTF_Name\tTF_Status\n"
        "M0001\tTFTEST\tD\n"
    )
    pwm_dir = root / "pwms_all_motifs"
    pwm_dir.mkdir(exist_ok=True)
    _write_acgt_pwm(pwm_dir / "M0001.txt")


def test_promoter_scan_gmt_build(tmp_path):
    pytest.importorskip("pyfaidx")

    # Genome: 200 bp on chr1, all 'A' except an ACGT motif at index 20..23.
    seq = list("A" * 200)
    seq[20:24] = list("ACGT")
    fasta = tmp_path / "genome.fa"
    fasta.write_text(">chr1\n" + "".join(seq) + "\n")

    # GENEP promoter window (up=60, +strand TSS=71 -> slice [11:71]) covers ACGT.
    # GENEN promoter window (TSS=171 -> slice [111:171]) does not.
    gtf = tmp_path / "genes.gtf"
    gtf.write_text(
        'chr1\tt\tgene\t71\t80\t.\t+\t.\tgene_name "GENEP";\n'
        'chr1\tt\tgene\t171\t180\t.\t+\t.\tgene_name "GENEN";\n'
    )

    bundle_root = tmp_path / "bundle"
    _make_synthetic_bundle(bundle_root)

    cfg = CisbpConfig(
        enabled=True,
        mode="gene_sets",
        gene_set_source="promoter_scan",
        data_dir=str(bundle_root),
        gtf=str(gtf),
        genome_fasta=str(fasta),
        promoter_upstream=60,
        promoter_downstream=0,
        motif_score_threshold=0.85,
        min_targets_per_tf=1,
    )
    gmt, gmt_path = gene_sets.resolve_gmt(
        cfg,
        cache_dir=tmp_path / "cache",
        gene_universe={"GENEP", "GENEN"},
        gtf=str(gtf),
        genome_fasta=str(fasta),
    )
    assert "TFTEST" in gmt
    assert gmt["TFTEST"] == ["GENEP"]
    assert gmt_path.is_file()  # cached

    # Second call uses cache (no rescan needed) and returns identical result.
    gmt2, _ = gene_sets.resolve_gmt(
        cfg, cache_dir=tmp_path / "cache",
        gene_universe={"GENEP", "GENEN"}, gtf=str(gtf), genome_fasta=str(fasta),
    )
    assert gmt2 == gmt


def test_context_defaults_genome_fasta_and_gtf_from_project():
    """genome_fasta defaults from step_config.alignment_qc; gtf from step_config.mapper."""
    import types

    from methyl_enricher.cli import _build_cisbp_context

    class _FakeProject:
        def get_step_config(self, name):
            return {
                "alignment_qc": {"genome_fasta": "/ref/hg38.fa"},
                "mapper": {"gtf": "/ref/annotation.gtf"},
            }.get(name, {})

    args = types.SimpleNamespace(cutoff=0.05)
    cfg = CisbpConfig(enabled=True, mode="gene_sets")  # no genome_fasta/gtf set
    ctx = _build_cisbp_context(args, cfg, _FakeProject(), project_path=None)
    assert ctx.genome_fasta == "/ref/hg38.fa"
    assert ctx.gtf == "/ref/annotation.gtf"

    # Explicit cisbp values override the project defaults.
    cfg2 = CisbpConfig(enabled=True, genome_fasta="/custom.fa", gtf="/custom.gtf")
    ctx2 = _build_cisbp_context(args, cfg2, _FakeProject(), project_path=None)
    assert ctx2.genome_fasta == "/custom.fa"
    assert ctx2.gtf == "/custom.gtf"


def test_resolve_bundle_local_dir(tmp_path):
    bundle_root = tmp_path / "bundle"
    _make_synthetic_bundle(bundle_root)
    bundle = resolve_bundle(data_dir=str(bundle_root), auto_download=False)
    assert bundle.is_complete()
    tf = bundle.load_tf_info()
    assert "TFTEST" in set(tf["TF_Name"])
    assert (tf["motif_evidence"] == "Direct").all()


def test_resolve_bundle_rechecks_cache_after_lock(tmp_path, monkeypatch):
    species = "Homo_sapiens"
    build = "3.10"
    cache_root = tmp_path / "cache" / "cisbp" / f"{species}_{build}"

    @contextmanager
    def _fake_lock(_path, **_kwargs):
        # Simulate another process completing cache while we waited for lock.
        _make_synthetic_bundle(cache_root)
        yield

    monkeypatch.setattr(download_mod, "_bundle_download_lock", _fake_lock)

    def _should_not_download(**_kwargs):
        raise AssertionError("download must not be called when cache completes during lock wait")

    monkeypatch.setattr(download_mod, "_download_species_zip", _should_not_download)

    bundle = resolve_bundle(
        species=species,
        build=build,
        cache_dir=str(tmp_path / "cache"),
        auto_download=True,
    )
    assert bundle.is_complete()
