---
name: data-type contract map
overview: >
  Map and adapt Portal to the wf.data_type contract that replaces
  workflow_action_schema JSON blobs. Fix deploy-order conflict, project
  types back to Draft-07 for viewers, and retarget Action Catalog / Designer.

> **Status: Implemented** — SQL contracts + Portal Action Catalog / Designer DM adapted.
> Re-run `deploy_azure.sh` (or apply `wf_data_type.sql` + `portal_workflow_api.sql` + `cfg_portal_api.sql`)
> then `smoke_data_type_portal_contract.sql`. Seed types via `methyl-cfg sync-actions`.

azure_devops:
  type: Feature
  title: "Portal adaptation to wf.data_type"
  epic_id: 413
todos:
  - id: verify-live-shape
    content: Verificar en Azure las columnas live de sp_list_workflow_actions / sp_get_data_type / counts de workflow_action_schema
    status: completed
  - id: fix-deploy-order
    content: Decidir y corregir conflicto portal_workflow_api vs wf_data_type para sp_list_workflow_actions
    status: completed
  - id: adapt-action-catalog
    content: Adaptar ActionCatalogDM/Frame al contrato workflow_actions + sp_get_data_type
    status: completed
  - id: adapt-schema-consumers
    content: "Adaptar Designer/NodeConfig: dejar de depender de Draft-07 rico; usar fields de data_type"
    status: completed
  - id: sync-cloud-export
    content: Re-exportar MethylpipelineCloud para que coincida con lo desplegado
    status: completed
---

# Contrato `wf.data_type` — mapa para adaptar Portal

## Intención

SoT relacional: `wf.data_type` + fields/enums; actions bind via `input_type_id` /
`output_type_id`. Git Pydantic schemas seed types; wire format stays JSON.

## Delivered

| Area | Change |
|------|--------|
| Deploy order | `portal_workflow_api.sql` no longer DROPs rich `sp_list_workflow_actions` |
| Projection | `wf.wf_repo_project_data_type_schema_json` → Draft-07 for Portal viewers |
| List/get actions | Rich row + `input_schema_json` / `output_schema_json` on list |
| Aliases | `sp_list_cfg_actions @published_only` → `@implemented_only` |
| Node config | `sp_list_workflow_nodes` / `sp_get_node_config` use type FKs + projection |
| Portal Action Catalog | Uses `sp_list_workflow_actions`; summary + schema views |
| Designer DM | `has_input_schema` tolerant; `GetActionSchema` via `sp_get_action_schema` |
| Smoke | `workflow_engine/sql_mssql/smoke_data_type_portal_contract.sql` |
| Cloud export | Matching procs/functions under MethylpipelineCloud |

## Ops

```bash
./workflow_engine/sql_mssql/deploy_azure.sh
# or apply: wf_data_type.sql, portal_workflow_api.sql, cfg_portal_api.sql
sqlcmd ... -i workflow_engine/sql_mssql/smoke_data_type_portal_contract.sql
methyl-cfg sync-actions   # seed types + bind FKs
```
