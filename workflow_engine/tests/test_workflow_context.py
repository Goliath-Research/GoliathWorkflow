"""Tests for workflow_context parameter derivation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))

from workflow_context import (  # noqa: E402
    build_resolved_config_scope_vars,
    compute_hyperparam_set_id,
    enrich_instance_context,
    list_unresolved_placeholders,
    resolved_config_scope_var_name,
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


def test_build_resolved_config_scope_vars_uses_profile_action_config():
    scope = build_resolved_config_scope_vars(
        {
            "actionConfig": {"detection": {"alpha": 0.01}},
            "siteConfig": {},
            "regulatory": {},
        }
    )
    key = resolved_config_scope_var_name("detection")
    assert key in scope
    assert scope[key].get("alpha") == 0.01


def test_build_resolved_config_scope_vars_merges_site_paths():
    """Site-derived paths merge into the resolved slice alongside profile knobs."""
    scope = build_resolved_config_scope_vars(
        {
            "actionConfig": {"mapper": {"csv_pattern": "dmps-*.csv"}},
            "siteConfig": {"annotation": {"gtf": "/ref/genes.gtf"}},
            "regulatory": {},
        }
    )
    mapper = scope[resolved_config_scope_var_name("mapper")]
    assert mapper.get("csv_pattern") == "dmps-*.csv"
    assert mapper.get("gtf") == "/ref/genes.gtf"


def test_build_resolved_config_scope_vars_profile_beats_site():
    """Profile actionConfig section wins over the site slice on a shared key."""
    scope = build_resolved_config_scope_vars(
        {
            "actionConfig": {"mapper": {"gtf": "/profile/genes.gtf"}},
            "siteConfig": {"annotation": {"gtf": "/site/genes.gtf"}},
            "regulatory": {},
        }
    )
    mapper = scope[resolved_config_scope_var_name("mapper")]
    assert mapper.get("gtf") == "/profile/genes.gtf"


def test_build_resolved_config_scope_vars_covers_all_catalog_keys():
    """Every catalog action_config_key gets a resolved scope var (no key dropped)."""
    import sys
    from pathlib import Path as _Path

    workers = _Path(__file__).resolve().parents[2] / "workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))
    from methyl_worker.action_catalog import ACTION_CATALOG

    scope = build_resolved_config_scope_vars(
        {"actionConfig": {}, "siteConfig": {}, "regulatory": {}}
    )
    for entry in ACTION_CATALOG:
        if entry.action_config_key:
            assert resolved_config_scope_var_name(entry.action_config_key) in scope


def test_compute_hyperparam_set_id_stable_and_label_sensitive():
    base = {
        "resolvedConfig__detection": {"alpha": 0.05},
        "resolvedConfig__validation": {"n_iterations": 10},
    }
    id_a = compute_hyperparam_set_id(base)
    id_b = compute_hyperparam_set_id(base)
    assert id_a == id_b
    labeled = {**base, "hyperparamSetName": "tier-a-baseline"}
    assert compute_hyperparam_set_id(labeled) != id_a


def test_finalize_instance_context_bakes_hyperparam_set_id():
    ctx = {
        "projectPath": "/work/projects/x/configs/project.json",
        "actionConfig": {"detection": {"alpha": 0.05}},
        "siteConfig": {},
        "regulatory": {},
    }
    ctx.update(build_resolved_config_scope_vars(ctx))
    ctx["hyperparamSetId"] = compute_hyperparam_set_id(ctx)
    assert len(ctx["hyperparamSetId"]) == 32
