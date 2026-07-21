"""libraryProtocol derivation for WGBS vs epi-GBS SamplePrep selection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_WE = _REPO / "workflow_engine"
if str(_WE) not in sys.path:
    sys.path.insert(0, str(_WE))
if str(_WE / "domain") not in sys.path:
    sys.path.insert(0, str(_WE / "domain"))

from pipeline_profiles import apply_pipeline_profile  # noqa: E402

_EPIGBS_PROGRAM = _REPO / "workflow_engine" / "domain" / "fixtures" / "sample_prep_epigbs.program.json"
_WGBS_PROGRAM = _REPO / "workflow_engine" / "domain" / "fixtures" / "sample_prep.program.json"


def test_library_protocol_epi_gbs_flags() -> None:
    out = apply_pipeline_profile(
        {},
        {
            "pipelineProfile": "epi_gbs",
            "actionConfig": {"sample_prep": {"library_protocol": "epi_gbs"}},
        },
    )
    assert out["libraryProtocol"] == "epi_gbs"
    assert out["useEpiGbs"] is True
    assert out["usePangenome"] is False


def test_library_protocol_wgbs_pangenome() -> None:
    out = apply_pipeline_profile(
        {},
        {
            "pipelineProfile": "custom",
            "actionConfig": {"sample_prep": {"library_protocol": "wgbs_pangenome"}},
        },
    )
    assert out["libraryProtocol"] == "wgbs_pangenome"
    assert out["usePangenome"] is True
    assert out["useEpiGbs"] is False


def test_skip_demultiplex_from_demux_config() -> None:
    out = apply_pipeline_profile(
        {},
        {
            "pipelineProfile": "epi_gbs",
            "actionConfig": {
                "sample_prep": {"library_protocol": "epi_gbs"},
                "demultiplex": {"skip": True},
            },
        },
    )
    assert out["skipDemultiplex"] is True


def test_epigbs_program_has_docker_align_not_parabricks() -> None:
    prog = json.loads(_EPIGBS_PROGRAM.read_text())
    text = json.dumps(prog)
    assert "sample.docker_align" in text
    assert "sample.demultiplex" in text
    assert "sample.parabricks_fq2bam" not in text
    assert "sample.parabricks_giraffe" not in text


def test_wgbs_sample_prep_unchanged_parabricks() -> None:
    prog = json.loads(_WGBS_PROGRAM.read_text())
    text = json.dumps(prog)
    assert "sample.parabricks_fq2bam" in text
    assert "sample.docker_align" not in text
