"""Tests for workflow_context parameter derivation."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))

from workflow_context import (  # noqa: E402
    apply_study_analyte,
    build_resolved_config_scope_vars,
    compute_execution_scope_id,
    enrich_instance_context,
    finalize_instance_context,
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


def test_enrich_instance_context_from_buffy_project(local_project):
    check = Path(__file__).resolve().parents[1] / "domain" / "checks" / "buffy_healthy_vs_pca"
    project_src = check / "configs" / "project_Buffy_healthy_vs_PCa.json"
    if not project_src.is_file():
        pytest.skip("buffy fixture project missing")

    project = local_project(project_src)
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


def test_compute_execution_scope_id_stable_and_label_sensitive():
    base = {
        "resolvedConfig__detection": {"alpha": 0.05},
        "resolvedConfig__validation": {"n_iterations": 10},
    }
    id_a = compute_execution_scope_id(base)
    id_b = compute_execution_scope_id(base)
    assert id_a == id_b
    labeled = {**base, "executionScopeName": "tier-a-baseline"}
    assert compute_execution_scope_id(labeled) != id_a


def test_compute_execution_scope_id_accepts_legacy_label_alias():
    base = {"resolvedConfig__detection": {"alpha": 0.05}}
    labeled = {**base, "hyperparamSetName": "tier-a-baseline"}
    assert compute_execution_scope_id(labeled) != compute_execution_scope_id(base)


def test_mssql_create_instance_sql_bakes_execution_scope_id() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "sql_mssql"
        / "wf_repository_api.sql"
    ).read_text(encoding="utf-8")
    create = sql.split("CREATE OR ALTER PROCEDURE wf.wf_repo_create_workflow_instance", 1)[1]
    create = create.split("CREATE OR ALTER PROCEDURE", 1)[0]
    assert "$.executionScopeId" in create
    assert "JSON_MODIFY" in create
    assert "wf_apply_execution_scope" in create
    # Empty executionScopeId must not block hyperparamSetId (per-field NULLIF).
    assert "NULLIF(LTRIM(RTRIM(JSON_VALUE(CAST(@ctx AS nvarchar(max)), N'$.executionScopeId'))), N'')" in create
    assert "NULLIF(LTRIM(RTRIM(JSON_VALUE(CAST(@ctx AS nvarchar(max)), N'$.hyperparamSetId'))), N'')" in create


def test_pg_create_instance_sql_falls_back_from_blank_execution_scope_id() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "sql_pg"
        / "02_repository_api.sql"
    ).read_text(encoding="utf-8")
    create = sql.split("CREATE OR REPLACE FUNCTION wf.wf_repo_create_workflow_instance(", 1)[1]
    create = create.split("CREATE OR REPLACE FUNCTION", 1)[0]
    assert "NULLIF(BTRIM(v_ctx->>'executionScopeId'), '')" in create
    assert "NULLIF(BTRIM(v_ctx->>'hyperparamSetId'), '')" in create
    assert "NULLIF(BTRIM(COALESCE(v_ctx->>'executionScopeId'" not in create


def test_apply_study_analyte_overrides_cfdna_seed() -> None:
    class _Proj:
        regulatory = {"primary_analyte": "buffy_coat"}

        def get_primary_analyte(self):
            return "buffy_coat"

    out = apply_study_analyte(
        {"primaryAnalyte": "cfdna", "isCfdna": True, "regulatory": {"primary_analyte": "buffy_coat"}},
        _Proj(),
    )
    assert out["primaryAnalyte"] == "buffy_coat"
    assert out["isCfdna"] is False


def test_apply_study_analyte_normalizes_case_and_hyphens() -> None:
    mixed = apply_study_analyte({"regulatory": {"primary_analyte": "Buffy_Coat"}})
    assert mixed["primaryAnalyte"] == "buffy_coat"
    assert mixed["isCfdna"] is False

    cfdna = apply_study_analyte({"regulatory": {"primary_analyte": "cfDNA"}})
    assert cfdna["primaryAnalyte"] == "cfdna"
    assert cfdna["isCfdna"] is True

    hyphen = apply_study_analyte({"regulatory": {"primary_analyte": "CF-DNA"}})
    assert hyphen["primaryAnalyte"] == "cf_dna"
    assert hyphen["isCfdna"] is True


def test_mssql_create_instance_sql_overlays_and_normalizes_study_analyte() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "sql_mssql"
        / "wf_repository_api.sql"
    ).read_text(encoding="utf-8")
    create = sql.split("CREATE OR ALTER PROCEDURE wf.wf_repo_create_workflow_instance", 1)[1]
    create = create.split("CREATE OR ALTER PROCEDURE", 1)[0]
    assert "default_analyte_id" in create
    assert "$.primaryAnalyte" in create
    assert "$.isCfdna" in create
    assert "REPLACE(LOWER(LTRIM(RTRIM(@analyte))), N'-', N'_')" in create
    assert "LOWER(@analyte) IN" not in create


def test_pg_create_instance_sql_overlays_and_normalizes_study_analyte() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "sql_pg"
        / "02_repository_api.sql"
    ).read_text(encoding="utf-8")
    create = sql.split("CREATE OR REPLACE FUNCTION wf.wf_repo_create_workflow_instance(", 1)[1]
    create = create.split("CREATE OR REPLACE FUNCTION", 1)[0]
    assert "default_analyte_id" in create
    assert "'primaryAnalyte'" in create
    assert "replace(lower(btrim(v_analyte)), '-', '_')" in create
    assert "lower(v_analyte) IN" not in create


def test_mssql_set_scope_variable_casts_json_for_either_column_type() -> None:
    repo = (
        Path(__file__).resolve().parents[1]
        / "sql_mssql"
        / "wf_repository_api.sql"
    ).read_text(encoding="utf-8")
    proc = repo.split("CREATE OR ALTER PROCEDURE wf.wf_repo_set_scope_variable", 1)[1]
    proc = proc.split("CREATE OR ALTER PROCEDURE", 1)[0]
    assert "@value_json json" in proc
    assert "CONVERT(nvarchar(max), @value_json)" in proc
    assert "CAST(@value_text AS json)" in proc
    assert "SET value_json = @value_json" not in proc
    assert "VALUES (@instance_id, @scope_exec_id, @var_name, @value_json)" not in proc

    writepath = (
        Path(__file__).resolve().parents[1]
        / "sql_mssql"
        / "wf_sql_scope_writepath_parity.sql"
    ).read_text(encoding="utf-8")
    setter = writepath.split("CREATE OR ALTER PROCEDURE wf.wf_set_scope_variable", 1)[1]
    setter = setter.split("CREATE OR ALTER PROCEDURE", 1)[0]
    assert "@value_json json" in setter
    assert "CONVERT(nvarchar(max), @value_json)" in setter
    assert "CAST(@value_text AS json)" in setter
    assert "@value_json AS value_json" not in setter


def test_mssql_json_alignment_boxes_scalars_then_alters_to_json() -> None:
    alignment = (
        Path(__file__).resolve().parents[1]
        / "sql_mssql"
        / "wf_json_column_alignment.sql"
    ).read_text(encoding="utf-8")
    assert "ALTER COLUMN value_json json NOT NULL" in alignment
    assert "ALTER COLUMN context_value_json json NULL" in alignment
    assert "wf.wf_json_box" in alignment
    assert '"$mp.v"' in alignment
    assert "ALTER COLUMN value_json nvarchar(max)" not in alignment


def test_mssql_db_script_worker_capabilities_use_json() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "sql_mssql"
        / "MethylPipelineDB_Script.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE OR ALTER FUNCTION wf.wf_worker_is_omnibus(@capabilities json)" in script
    assert "DECLARE @worker_capabilities json;" in script
    assert "@worker_capabilities NVARCHAR" not in script
    assert "@output_json json NULL" in script
    assert "output_json = @oj" not in script


def test_pg_workflow_edge_unique_is_parent_child_not_order() -> None:
    schema = (
        Path(__file__).resolve().parents[1]
        / "sql_pg"
        / "00_schema.sql"
    ).read_text(encoding="utf-8")
    assert "DROP INDEX IF EXISTS wf.uq_we_parent_child_order" in schema
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_we_parent_child" in schema
    assert "ON wf.workflow_edge (parent_node_id, child_node_id)" in schema
    assert "UNIQUE INDEX IF NOT EXISTS uq_we_parent_child_order" not in schema


def test_mssql_exec_does_not_pass_json_box_as_proc_arg() -> None:
    """T-SQL EXEC cannot take a function call as a named parameter."""
    root = Path(__file__).resolve().parents[1] / "sql_mssql"
    hits: list[str] = []
    for path in root.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        if "@value_json = wf.wf_json_box(" in text.replace("\n", " "):
            hits.append(path.name)
        if "@value_json = wf.wf_json_box(" in text:
            hits.append(path.name)
    assert hits == [], f"EXEC @value_json = wf.wf_json_box(...) is illegal T-SQL: {hits}"

    isnull_hits = [
        path.name
        for path in root.glob("*.sql")
        if "@from_scope_exec_id = ISNULL(" in path.read_text(encoding="utf-8")
    ]
    assert isnull_hits == [], (
        "EXEC named args cannot take ISNULL(...): " + ", ".join(isnull_hits)
    )

    expr_hits: list[str] = []
    expr_re = re.compile(r"@iteration_no\s*=\s*@\w+\s*\+")
    for path in root.glob("*.sql"):
        if expr_re.search(path.read_text(encoding="utf-8")):
            expr_hits.append(path.name)
    assert expr_hits == [], (
        "EXEC named args cannot take @var + N: " + ", ".join(expr_hits)
    )


def test_finalize_instance_context_bakes_execution_scope_id():
    ctx = {
        "projectPath": "/work/projects/x/configs/project.json",
        "actionConfig": {"detection": {"alpha": 0.05}},
        "siteConfig": {},
        "regulatory": {},
    }
    ctx.update(build_resolved_config_scope_vars(ctx))
    ctx["executionScopeId"] = compute_execution_scope_id(ctx)
    assert len(ctx["executionScopeId"]) == 32


def _patch_finalize_seams(monkeypatch, *, alignment_mode="linear", engine="mojo"):
    we = Path(__file__).resolve().parents[1]
    if str(we) not in sys.path:
        sys.path.insert(0, str(we))
    import cfg.sync_on_start as sync_on_start  # noqa: E402

    monkeypatch.setattr(sync_on_start, "ensure_study_work_synced", lambda ctx: dict(ctx))
    monkeypatch.setattr(
        "workflow_context.enrich_instance_context",
        lambda ctx: {
            **ctx,
            "alignmentMode": alignment_mode,
            "actionConfig": {"parabricks": {"engine": engine}},
        },
    )
    monkeypatch.setattr("methyl_utils.modality_gate.enforce_pack_pairing", lambda ctx: None)
    monkeypatch.setattr(
        "methyl_utils.modality_gate.enforce_study_primary_analyte", lambda ctx: None
    )
    monkeypatch.setattr("workflow_context.build_resolved_config_scope_vars", lambda ctx: {})


def test_finalize_instance_context_binds_sample_arms(tmp_path: Path, monkeypatch) -> None:
    _patch_finalize_seams(monkeypatch)
    root = tmp_path / "samples" / "S1"
    root.mkdir(parents=True)
    out = finalize_instance_context(
        {
            "projectPath": str(tmp_path / "project.json"),
            "samples": [
                {"sampleId": "S1", "sampleDir": str(root), "sampleRoot": str(root)}
            ],
        }
    )
    assert out["samples"][0]["sampleDir"].endswith("align.linear.mojo")
    assert Path(out["samples"][0]["sampleRoot"]).resolve() == root.resolve()


def test_finalize_instance_context_skips_rnaseq_arm_bind(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_finalize_seams(monkeypatch)
    root = tmp_path / "samples" / "S1"
    root.mkdir(parents=True)
    out = finalize_instance_context(
        {
            "projectPath": str(tmp_path / "project.json"),
            "program_path": str(tmp_path / "sample_prep_rnaseq.program.json"),
            "samples": [
                {"sampleId": "S1", "sampleDir": str(root), "sampleRoot": str(root)}
            ],
        }
    )
    assert out["samples"][0]["sampleDir"] == str(root)
    assert "align." not in out["samples"][0]["sampleDir"]
