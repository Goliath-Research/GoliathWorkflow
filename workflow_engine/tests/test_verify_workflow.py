"""Tests for SamplePrep / DomainProgram structural verification."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOMAIN = REPO / "workflow_engine" / "domain"
sys.path.insert(0, str(DOMAIN))

from verify_workflow import (  # noqa: E402
    verify_compiled_workflow,
    verify_methylgrapher_bake,
    verify_program_file,
)
from compiler import compile_domain_program_file  # noqa: E402


def test_sample_prep_graph_ok() -> None:
    report = verify_program_file(DOMAIN / "fixtures" / "sample_prep.program.json")
    assert report.ok, report.to_dict()
    assert report.node_count >= 50
    assert "sample.methylgrapher_wgbs_align" in report.action_names
    assert "sample.parabricks_fq2bam" in report.action_names


def test_if_without_else_still_has_else_edge() -> None:
    """Compiler emits empty ELSE; verifier requires THEN+ELSE."""
    result = compile_domain_program_file(
        DOMAIN / "fixtures" / "sample_prep.program.json", enrich_context=False
    )
    report = verify_compiled_workflow(result)
    assert not any(f.code == "if_missing_else" for f in report.findings)


def test_methylgrapher_bake_from_site_file() -> None:
    site_path = Path("/work/site/methyl_site.json")
    if not site_path.is_file():
        pytest.skip("no /work/site/methyl_site.json")
    import json

    site = json.loads(site_path.read_text(encoding="utf-8"))
    proc = json.loads(
        (
            DOMAIN
            / "profiles"
            / "procedures"
            / "buffy_wgbs_pangenome_gene_fc.procedure.json"
        ).read_text(encoding="utf-8")
    )
    findings = verify_methylgrapher_bake(site, proc.get("actionConfig"))
    assert not findings, [f.message for f in findings]
