# JSON Schema Property Editor (Delphi VCL 11+)

Generic JSON editor driven entirely by JSON Schema. Loads schema files and edits any matching JSON document using a **recursive property editor**: one row per property, with modal nested editors for objects, arrays, and dictionaries.

No Delphi class codegen — JSON Schema artifacts drive the UI at runtime. The editor is **blind to the purpose of the JSON**; nested or complex types must be described in schema (including `$ref` to other schema files).

## Requirements

- Delphi 11 or later (VCL, Win32/Win64)
- [Spring4D](https://bitbucket.org/sglienke/spring4d) (IoC container for property-editor resolution)
- DUnitX (for tests, optional)

Add Spring4D library paths to the Delphi IDE (or project search path), at minimum:

- `Spring4D/source/Core`
- `Spring4D/source/Base`
- `Spring4D/source/Data`
- `Spring4D/source/Container`

All in-memory collections use **Spring4D** (`Spring.Collections.IList`, `IDictionary`) via `TCollections.CreateList`, `CreateObjectList`, and `CreateDictionary`. Class lists that own their elements use `TCollections.CreateObjectList<T>(True)`; non-owning references (for example `oneOf` branches) use `CreateObjectList<T>(False)`.

Custom sorting passes an anonymous comparison function directly to **`IList<T>.Sort`**.

## Build

1. Open [`MethylConfigEditor.dproj`](MethylConfigEditor.dproj) in Delphi.
2. Build **Win64** or **Win32**.
3. On first run, set **Schemas root** to a directory containing `*.schema.json` files (Browse… or edit the path). Settings persist in `methyl-config-editor.ini` next to the executable.

## Usage

1. Select a schema from the dropdown (all `*.schema.json` files under the schemas root).
2. **File → Open JSON** to load a document (or start from `{}` and use **Edit → Edit properties**).
3. **Edit → Edit properties** opens the root property editor.
4. Complex fields show **Edit…** and open nested editors modally.
5. **File → Save JSON** writes pretty-printed UTF-8 JSON.

## Workflow action schemas (remote catalog)

The worker gateway (`methyl-gateway`) is **claim/submit only** and does **not** expose `/v1/actions`.

Prefer one of:

1. **Filesystem schemas** under **Schemas root** (`schemas/tasks/*.schema.json`, `schemas/domain/*`).
2. **Portal / wf SQL** — list actions via `portal.sp_list_workflow_actions` / `portal.sp_get_workflow_action` (aliases `sp_list/get_cfg_action`); describe types via `portal.sp_get_data_type` / fields (explicit `wf.data_type`, not schema blobs).
3. Legacy ini `[Gateway] BaseUrl=.../v1` remote catalog is **deprecated**; do not point the editor at the worker gateway for action schemas.

`TSchemaValidator.AllowTemplatePlaceholders` (default **true**) accepts string values matching `${...}` for any declared type so unresolved template tokens validate at edit time.

| Unit | Role |
|------|------|
| `Schema/RemoteSchemaCatalog.pas` | HTTP client (legacy; prefer cfg/portal or filesystem) |
| `App/SchemaCatalog.pas` | Merges filesystem + optional remote entries |
| `Schema/SchemaValidator.pas` | Optional `${...}` placeholder tolerance |

## Architecture

Property editing uses **Spring4D `GlobalContainer`** to resolve an `ISchemaPropertyEditor` by schema shape (or optional title override).

```text
JSON Schema file(s)  →  JsonSchemaLoader ($ref including relative files)
                     →  TSchemaNode meta-tree
JSON document        →  PropertyEditorForm (recursive rows)
                     →  SchemaEditorRegistry.Resolve(node)
                     →  GlobalContainer.Resolve<ISchemaPropertyEditor>(kindKey)
```

| Unit | Role |
|------|------|
| `UI/Editors/EditorTypes.pas` | `ISchemaPropertyEditor`, `TPropertyRow` |
| `UI/Editors/SchemaEditorRegistry.pas` | Resolve editor by schema node |
| `UI/Editors/SchemaEditorRegistration.pas` | Register editors with Spring4D at startup |
| `Schema/JsonSchemaLoader.pas` | Parse schema, `$ref` (internal and relative file), nullable `anyOf`, `oneOf`+`discriminator` |
| `Schema/SchemaNode.pas` | Internal schema meta-tree |
| `Schema/SchemaDocumentCache.pas` | Owned cache of loaded schema documents |
| `Data/JsonPath.pas` | JSON pointer get/set |
| `Data/JsonArrayOps.pas` | Shared `TJSONArray` replace/remove/move helpers |
| `UI/PropertyEditorForm.pas` | Recursive property grid shell (objects and open maps) |
| `UI/ArrayEditorForm.pas` | Array list editor |
| `App/MainForm.pas` | Schema catalog, document load/save |
| `Schema/RemoteSchemaCatalog.pas` | Fetch action schemas from workflow REST gateway |

### Nested types via `$ref`

Relative file references are resolved against the directory of the schema file being loaded, for example:

- `other.schema.json`
- `./definitions/widget.schema.json#/properties/name`

No property-name conventions or domain-specific filename mapping exist in the editor.

### Adding a custom editor

1. Implement `ISchemaPropertyEditor` (subclass `TAbstractSchemaEditor`).
2. Add a string constant in `SchemaEditorKeys` if it is a new *kind* key.
3. Register in `SchemaEditorRegistration.EnsureRegistered`:

```delphi
GlobalContainer.RegisterType<ISchemaPropertyEditor, TMyCustomSchemaEditor>
  ('myCustomKey').AsTransient;
```

4. Optional: register by JSON Schema **`title`** only when you intentionally want a schema-specific override **and** register the same string in Spring (ordinary field titles such as `"Batch"` are not looked up):

```delphi
GlobalContainer.RegisterType<ISchemaPropertyEditor, TMyCustomSchemaEditor>
  ('MySchemaTitle').AsTransient;
```

Resolution order: optional **title** override only when that title string is explicitly registered in Spring (not ordinary JSON Schema titles), then **kind** key from `TSchemaEditorKeys.ForNode`.

## Tests

Open [`tests/MethylConfigEditorTests.dpr`](tests/MethylConfigEditorTests.dpr) in Delphi (requires DUnitX).

```text
MethylConfigEditorTests.exe
```

Tests cover schema loading (including `$ref`), JSON path utilities, and array operations.

## Study configuration (four-layer model)

Author pipeline studies with four artifacts (no `step_config` in study manifests):

| Layer | Typical path | Owns |
|-------|----------------|------|
| Study manifest | `configs/project_*.json` | Cohorts, comparisons, paths, `regulatory`, `validation_partitions`, `progression_order` |
| Pipeline profile | `configs/*.profile.json` or repo `workflow_engine/domain/profiles/` | `actionConfig` tool parameters + scope booleans (`runDmpSelection`, …) |
| Site manifest | `configs/site_grch38.example.json` or `/work/site/methyl_site.json` | Genomes, GTF, caches, cluster defaults |
| DomainProgram | repo `workflow_engine/domain/**/*.program.json` | Control flow, per-action `with` / `stepOverride` |

**Schemas root** should include:

- `schemas/config/project_config.schema.json` — study manifest
- `schemas/config/profile.schema.json` — pipeline profile
- `schemas/config/site_manifest.schema.json` — site manifest

Open each JSON type with the matching schema from the dropdown. Tool tuning belongs in **profile** `actionConfig`, not in the study manifest.

Legacy projects with `step_config` can be converted once:

```bash
python scripts/migrate_project_config.py --in-place path/to/project_*.json
```

## Example configs

The [`configs/`](configs/) folder may contain sample JSON documents for manual testing. They are not part of the tool design.

## Web application (uniGUI)

A uniGUI web port lives alongside the VCL desktop app in [`MethylConfigEditorWeb.dproj`](MethylConfigEditorWeb.dproj). It reuses the shared **Schema**, **Data**, and validation units and replaces the hand-built VCL property grid with **TUniPropertyGrid**.

### Web requirements

- Delphi 11 or later
- [uniGUI](https://www.unigui.com/) (StandAlone Server or HyperServer)
- [Spring4D](https://bitbucket.org/sglienke/spring4d) (collections in schema/data layers only; no Spring IoC in the web UI)
- DUnitX (optional, for tests)

### Build and run (StandAlone Server)

1. Open [`MethylConfigEditorWeb.dproj`](MethylConfigEditorWeb.dproj) in Delphi with uniGUI installed.
2. Build **Win64**.
3. Copy [`methyl-config-editor-web.ini`](methyl-config-editor-web.ini) next to the executable (or edit after first run).
4. Set `Paths.SchemasRoot` to the server directory containing `*.schema.json` (default: `..\..\schemas\config` relative to the exe).
5. Run `MethylConfigEditorWeb.exe` and open `http://localhost:8077` (port from `[Server] Port` in the INI).

### Web usage

1. Select a schema from the dropdown (loaded from the server schemas root).
2. **Upload JSON** to load a document, or **New JSON** to create defaults from the schema.
3. **Edit properties** opens a `TUniPropertyGrid` driven by the schema. Scalar fields edit inline; complex fields (objects, arrays, dictionaries) show a `>>` summary — click the row to open a nested editor.
4. **Download JSON** saves pretty-printed UTF-8 JSON to the browser.

### Web architecture

| Unit | Role |
|------|------|
| `Web/MainForm.pas` | Schema picker, JSON preview, upload/download |
| `Web/SchemaPropertyGrid.pas` | `TSchemaPropertyGridController` — `Clear` / `AddProperty` / `OnPropertyChange` |
| `Web/NestedEditorForm.pas` | Modal object/dictionary editor with nested grid |
| `Web/WebArrayEditorForm.pas` | Array list editor |
| `Web/SchemaEditorService.pas` | Root value dispatch (object / array / scalar wrapper) |
| `Core/JsonValueParsing.pas` | Shared string ↔ `TJSONValue` parsing for grid edits |

### Deployment (HyperServer)

For production, deploy the built executable with:

- `methyl-config-editor-web.ini` (schemas root and port)
- Access to `schemas/config/` on the host
- HyperServer or Windows service wrapper per [uniGUI deployment docs](https://www.unigui.com/doc/online_help/deployment.html)

The VCL desktop app remains available for parity testing until the web app is validated; then retire `MethylConfigEditor.dproj` as the default editor.
