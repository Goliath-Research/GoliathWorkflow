---
name: Portal UI SQL Actions
overview: Walk the EpiPortal IA tree (six roles, six nav floors) and give every leaf a `portal.sp_*` contract. Most screens already have procs; this plan implements the instance-67 gaps (study link, storage, guardrail overlay, sample progress, fail/cancel run or action) plus the remaining Admin/HPO wrappers so EpiPortal never writes `wf`/`RBAC`/`Contract` tables directly.

> **Status: IMPLEMENTED.** MSSQL + PG `portal.sp_*` for study link/storage/overlay, instance monitor, fail/cancel/stop, Admin BypassScope, contract setters, and HPO promote. EpiPortal screens remain in the other repo.

azure_devops:
  type: Feature
  title: "Portal UI SQL actions per leaf"
  epic_id: 413
todos:
  - id: sql-study-link-storage
    content: portal.sp_link_study_instance; extend sp_create_and_start_instance with @study_row_id; sp_get/set_study_storage (MSSQL+PG + db_objects.yaml)
    status: completed
  - id: sql-guardrail-overlay
    content: portal.sp_get/set_study_action_config_overlay on cfg.study (next-run actionConfig; no mid-run rebake)
    status: completed
  - id: sql-instance-monitor
    content: sp_get_workflow_instance_header, sp_get_instance_config (redacted), sp_get_instance_sample_progress
    status: completed
  - id: sql-fail-cancel-stop
    content: sp_cancel_instance, sp_fail_instance, sp_fail_node, sp_stop_node (drain queued; stop in-flight only if can_stop)
    status: completed
  - id: sql-admin-hpo-holes
    content: BypassScope approval CRUD, session revoke, contract scope/limit/policy setters, HPO promote-winner, MSSQL sp_list_data_type_fields
    status: completed
  - id: docs-ia-plan
    content: Refresh portal-ia.md + canvas inventory; promote plan to docs/plans and README under AB#413
    status: completed
---

# Portal UI tree: stored procedures per leaf

> **Status: IMPLEMENTED.** Feature under Epic **AB#413**. This repo owns the **SQL contracts**; EpiPortal Delphi/uniGUI screens stay in the other repo.

Canonical IA: [docs/architecture/portal-ia.md](../architecture/portal-ia.md).

SQL twins:

- [workflow_engine/sql_mssql/portal_study_ops_api.sql](../../workflow_engine/sql_mssql/portal_study_ops_api.sql)
- [workflow_engine/sql_pg/portal_study_ops_api.sql](../../workflow_engine/sql_pg/portal_study_ops_api.sql)

Operator error codes: `4097` `OPERATOR_CANCELLED`, `4098` `OPERATOR_FAILED`, `4099` `WORKER_STOPPED`.

Heartbeat honors `wf.node_execution.stop_requested` as `command=STOP` (distinct from fleet `desired_state`).

See the Screen → procedure inventory in [portal-ia.md](../architecture/portal-ia.md).
