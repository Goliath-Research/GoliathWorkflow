# MethylPipeline Config Editor (Delphi VCL 11+)

Dynamic JSON config editor for MethylPipeline. Loads committed JSON Schema artifacts from [`schemas/config/`](../../schemas/config/) and edits any matching JSON document using a **recursive property editor**: one row per property, with modal nested editors for objects, arrays, and dictionaries.

No Delphi class codegen — schemas from `methyl-export-config-schemas` drive the UI at runtime.

## Requirements

- Delphi 11 or later (VCL, Win32/Win64)
- [Spring4D](https://bitbucket.org/sglienke/spring4d) (IoC container for property-editor resolution)
- DUnitX (for tests, optional)

Add Spring4D library paths to the Delphi IDE (or project search path), at minimum:

- `Spring4D/source/Core`
- `Spring4D/source/Base` (provides `Generics.Defaults` / `Generics.Collections` used alongside the RTL)
- `Spring4D/source/Data`
- `Spring4D/source/Container`

Ensure **Spring `Base` precedes the RTL** in the library search path so `Generics.Defaults` resolves to Spring4D’s comparer types (same names as the RTL, different units).

For custom list sorting, use **`TComparer<T>.Construct(...)`**, not `.Default(...)`. Spring’s `.Default` returns a built-in comparer for types that have one; it is not a factory that accepts an anonymous comparison function.

## Build

1. Open [`MethylConfigEditor.dproj`](MethylConfigEditor.dproj) in Delphi.
2. Build **Win64** or **Win32**.
3. On first run, set **Schemas root** to the repo `schemas/config` directory (Browse… or edit the path). Settings persist in `methyl-config-editor.ini` next to the executable.

Default relative path from `Win64\Debug\`: `..\..\..\schemas\config`.

## Usage

1. Select a schema from the dropdown (all `*.schema.json` files under the schemas root).
2. **File → Open JSON** to load a config file (or start from `{}` and use **Edit → Edit properties**).
3. **Edit → Edit properties** opens the root property editor.
4. Complex fields show **Edit…** and open the same property editor (or array/dictionary shells) modally.
5. **File → Save JSON** writes pretty-printed UTF-8 JSON.

## Architecture

Property editing uses **Spring4D `GlobalContainer`** to resolve an `ISchemaPropertyEditor` implementation by name. Each schema shape has its own editor class; `TPropertyEditorForm` only builds rows and delegates to the resolved editor.

```text
TSchemaEditorKeys.ForNode(schemaNode)  →  editor key (e.g. "string", "object")
GlobalContainer.ResolveNamed<ISchemaPropertyEditor>(key)
  → TStringSchemaEditor / TObjectSchemaEditor / ...
```

| Unit | Role |
|------|------|
| `UI/Editors/EditorTypes.pas` | `ISchemaPropertyEditor`, `TPropertyRow` |
| `UI/Editors/SchemaEditorRegistry.pas` | Resolve editor by schema node (or `$ref` path override) |
| `UI/Editors/SchemaEditorRegistration.pas` | Register all editors with Spring4D at startup |
| `UI/Editors/*SchemaEditor.pas` | One class per kind (string, enum, object, array, …) |
| `Schema/JsonSchemaLoader.pas` | Parse schema, `$ref`/`$defs`, nullable `anyOf`, `oneOf`+`discriminator` |
| `Schema/SchemaNode.pas` | Internal schema meta-tree |
| `Data/JsonPath.pas` | JSON pointer get/set |
| `UI/PropertyEditorForm.pas` | Recursive property grid shell (rows + validation) |
| `UI/ArrayEditorForm.pas` | Array list + nested object editor |
| `UI/DictEditorForm.pas` | Open `additionalProperties` maps |
| `App/MainForm.pas` | Schema catalog, document load/save |

### Adding a custom editor

1. Implement `ISchemaPropertyEditor` (subclass `TAbstractSchemaEditor`).
2. Define a unique `EditorKey` string constant in `SchemaEditorKeys`.
3. Register in `SchemaEditorRegistration.EnsureRegistered`:

```delphi
GlobalContainer.RegisterType<ISchemaPropertyEditor, TMyCustomSchemaEditor>
  .Named('myCustomKey').AsTransient;
```

4. Optional: register by JSON Schema `$ref` path or model **`title`** for a specific Pydantic model:

```delphi
GlobalContainer.RegisterType<ISchemaPropertyEditor, TDetectionStepEditor>
  .Named('MethylDetectorConfig').AsTransient;
```

`TSchemaEditorRegistry.Resolve` checks `$ref`, then **`title`**, then kind-based keys.

### Example: `TDetectionStepEditor`

Registered as `MethylDetectorConfig` (matches `detection.schema.json` root title). Used when:

- Editing a document with **detection.schema.json** selected as the active schema.
- Editing **`step_config.detection`** inside `project_config.schema.json` (property name `detection` maps to the typed step loader).

The editor shows a compact summary (`chromosome=…; centroids set`) and opens the full recursive property form against the committed **detection** schema, not the loose `step_config` placeholder in the project schema.

Add more typed step editors by mirroring [`DetectionStepEditor.pas`](src/UI/Editors/DetectionStepEditor.pas) and registering in [`SchemaEditorRegistration.pas`](src/UI/Editors/SchemaEditorRegistration.pas); extend [`TypedStepSchemas.pas`](src/Schema/TypedStepSchemas.pas) step id → filename mapping.

## Tests

Open [`tests/MethylConfigEditorTests.dpr`](tests/MethylConfigEditorTests.dpr) in Delphi (requires DUnitX). Tests load fixtures from `schemas/config/` relative to the repo root.

Run from IDE or:

```text
MethylConfigEditorTests.exe
```

## Schema updates

When Pydantic models change in the Python repo:

```bash
methyl-export-config-schemas
```

Point the editor at the updated `schemas/config/` — no Delphi rebuild required for new fields (only if UI/schema parser logic changes).
