---
name: DataType Action Editor
overview: >
  Replace the Action catalog JSON tree (Draft-07 projection + TJsonViewer / josdejong)
  with the methyl-config-editor Web property grid, driven from wf.data_type fields
  instead of schema blobs. Catalog stays read-only; JSON remains the wire encoding only.

> **Status: Implemented.** Action catalog inspects input/output DataTypes with a
> read-only TUniPropertyGrid. Types load via `portal.sp_get_data_type` on a second
> connection (no MARS). Draft-07 `input_schema_json` is no longer consumed by this screen.

azure_devops:
  type: Feature
  title: "DataType-driven editor in Action catalog"
  epic_id: 413
todos:
  - id: loader
    content: "Add DataTypeSchemaLoader: sp_get_data_type (+ nested types) → TSchemaNode, with kind/enum/array mapping and name cache"
    status: completed
  - id: share-units
    content: Wire methyl-config-editor Schema/Data/Core/Web grid units + Spring4D into EPORTAL.dproj; host TUniPropertyGrid with ReadOnly
    status: completed
  - id: mars-conn
    content: Second UniConnection + type cache so Action catalog can fetch types while qActions stays open
    status: completed
  - id: catalog-ui
    content: "ActionCatalogFrame: drop JSON views; input/output use DataType property grid; Open full reuses NestedEditorForm read-only"
    status: completed
  - id: plan-docs
    content: Promote plan to docs/plans and note Action catalog no longer consumes projected Draft-07
    status: completed
---

# DataType-driven editor in Action catalog

## What is true today (pre-change)

After the BD cutover, **types live in** `wf.data_type` + `wf.data_type_field` + `wf.data_type_enum_value`. Actions bind by **name** via `input_type_id` / `output_type_id`. JSON Schema blobs on `wf.workflow_action_schema` are retired; JSON is only the **wire** encoding ([action-provider-registry](../architecture/action-provider-registry.md)).

The Portal **did not switch the UI**. It still projected types back to Draft-07 for `TJsonViewer` / `TfrmJsonEditor`. That viewer bridge is retired on this screen.

## Delivered

| Area | Change |
|------|--------|
| Loader | [`DataTypeSchemaLoader.pas`](../../tools/methyl-config-editor/src/Schema/DataTypeSchemaLoader.pas) maps `portal.sp_get_data_type` rows to `TSchemaNode` |
| Preview | `TSchemaDefaults.CreatePreviewValue` fills every field (cycle-safe) for catalog browse |
| Grid | `TSchemaPropertyGridController.ReadOnly` + NestedEditorForm / WebArrayEditorForm `AReadOnly` |
| Portal host | [`DataTypeEditorHost.pas`](../../../Portal/DataTypeEditorHost.pas) |
| MARS | [`ActionCatalogDM`](../../../Portal/ActionCatalogDM.pas) second `TUniConnection` + loader cache |
| Action catalog | input/output type views; Open full is the same widget read-only |
| Tests | `DataTypeSchemaLoaderTests` |

## Out of scope (follow-ups)

- DataType Registry screen
- Study Control / Site / Profile JSON viewers
- Designer `GetActionSchema` Draft-07
- Saving types from the catalog
- Standalone MethylConfigEditorWeb SQL wiring
