"""Sample prep pangenome aligner branch compile checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))

from compiler import compile_domain_program_file  # noqa: E402


def _load(name: str):
    return json.loads((Path(__file__).resolve().parents[1] / "domain" / "fixtures" / name).read_text())


def test_sample_prep_compiles_with_pangenome_branch() -> None:
    program_path = Path(__file__).resolve().parents[1] / "domain" / "fixtures" / "sample_prep.program.json"
    result = compile_domain_program_file(program_path, enrich_context=False)
    wf = result.workflow
    action_names = [n.action_name for n in wf.nodes if n.node_type == "ACTION"]
    assert "sample.parabricks_fq2bam" in action_names
    assert "sample.parabricks_giraffe" in action_names


def test_pipeline_profiles_seed_use_pangenome_from_alignment_mode() -> None:
    from pipeline_profiles import seed_pipeline_scope_flags

    ctx = seed_pipeline_scope_flags(
        {"pipelineProfile": "legacy_dual"},
        action_config={"parabricks": {"alignment_mode": "pangenome"}},
    )
    assert ctx["alignmentMode"] == "pangenome"
    assert ctx["usePangenome"] is True

    linear = seed_pipeline_scope_flags(
        {"pipelineProfile": "legacy_dual"},
        action_config={"parabricks": {"alignment_mode": "linear"}},
    )
    assert linear["usePangenome"] is False


def test_pipeline_profiles_seed_delete_fastqs_default_and_override() -> None:
    from pipeline_profiles import seed_pipeline_scope_flags

    default = seed_pipeline_scope_flags({"pipelineProfile": "legacy_dual"}, action_config={})
    assert default["deleteFastqs"] is True

    retain = seed_pipeline_scope_flags(
        {"pipelineProfile": "legacy_dual"},
        action_config={"sample_prep": {"delete_fastqs": False}},
    )
    assert retain["deleteFastqs"] is False

    explicit = seed_pipeline_scope_flags(
        {"pipelineProfile": "legacy_dual", "deleteFastqs": False},
        action_config={"sample_prep": {"delete_fastqs": True}},
    )
    assert explicit["deleteFastqs"] is False


def test_sample_prep_delete_fastqs_gated_in_program() -> None:
    program = _load("sample_prep.program.json")
    assert "deleteFastqs" in program["variables"]
    text = json.dumps(program)
    assert text.count('"sample.delete_fastqs"') == 6
    assert text.count('"${deleteFastqs}"') == 6


def test_pipeline_profiles_empty_alignment_mode_uses_profile_fallback() -> None:
    from pipeline_profiles import seed_pipeline_scope_flags

    ctx = seed_pipeline_scope_flags(
        {"pipelineProfile": "legacy_dual", "alignmentMode": ""},
        action_config={"parabricks": {"alignment_mode": "pangenome"}},
    )
    assert ctx["alignmentMode"] == "pangenome"
    assert ctx["usePangenome"] is True
