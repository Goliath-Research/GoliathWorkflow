"""Tests for workflow_context parameter derivation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))

from workflow_context import (  # noqa: E402
    enrich_instance_context,
    list_unresolved_placeholders,
    resolve_input_json_from_template,
    validate_resolved_input_json,
)


def test_list_unresolved_placeholders_finds_var_refs():
    assert list_unresolved_placeholders({"chromosome": "${var.chromosome}"}) == ["chromosome"]


def test_resolve_input_json_from_template():
    template = {
        "tool": "MethylCentroid",
        "project": "${var.projectPath}",
        "chromosome": "${var.chromosome}",
    }
    resolved = resolve_input_json_from_template(
        template,
        {"projectPath": "/work/p/project.json", "chromosome": "21"},
    )
    assert resolved["project"] == "/work/p/project.json"
    assert resolved["chromosome"] == "21"


def test_validate_resolved_input_json_rejects_placeholders():
    errors = validate_resolved_input_json(
        {"tool": "MethylCentroid", "chromosome": "${var.chromosome}"},
        "pipeline.centroid",
    )
    assert any("unresolved" in e for e in errors)


def test_enrich_instance_context_from_buffy_project():
    check = Path(__file__).resolve().parents[1] / "domain" / "checks" / "buffy_healthy_vs_pca"
    project = check / "configs" / "project_Buffy_healthy_vs_PCa.json"
    if not project.is_file():
        pytest.skip("buffy fixture project missing")

    enriched = enrich_instance_context({"projectPath": str(project)})
    assert enriched.get("comparisons")
    assert enriched.get("chromosomes")
    assert enriched.get("centroid1Dir")
    first = enriched["comparisons"][0]
    assert "detectOutDir" in first
    assert "centroid2Dir" in first
