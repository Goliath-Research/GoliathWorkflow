# MethylPipeline Config Editor (Delphi VCL 11+)

Dynamic JSON config editor for MethylPipeline. Loads committed JSON Schema artifacts from [`schemas/config/`](../../schemas/config/) and edits any matching JSON document using a **recursive property editor**: one row per property, with modal nested editors for objects, arrays, and dictionaries.

No Delphi class codegen — schemas from `methyl-export-config-schemas` drive the UI at runtime.

## Requirements

- Delphi 11 or later (VCL, Win32/Win64)
- [Spring4D](https://bitbucket.org/sglienke/spring4d) (IoC container for property-editor resolution)
- DUnitX (for tests, optional)

Add Spring4D library paths to the Delphi IDE (or project search path), at minimum:

- `Spring4D/source/Core`
- `Spring4D/source/Base`
- `Spring4D/source/Data`
- `Spring4D/source/Container`

All in-memory collections use **Spring4D** (`Spring.Collections.IList`, `IDictionary`) via `TCollections.CreateList`, `CreateObjectList`, and `CreateDictionary`. Class lists that own their elements use `TCollections.CreateObjectList<T>(True)`; non-owning references (for example `oneOf` branches) use `CreateObjectList<T>(False)`. Dictionary values that are heap objects (cached schema documents) are freed explicitly before `Clear`, matching the existing `TypedStepSchemas` pattern.

Sorting uses **`Spring.Comparers.TComparer<T>.Construct(...)`** with an anonymous comparison function. Do not use `.Default(...)` when you need a custom comparator — `.Default` returns a built-in comparer when one exists; it is not a factory for lambdas.

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

Property editing uses **Spring4D `GlobalContainer`** to resolve an `ISchemaPropertyEditor` implementation by name. Each schema *shape* (string, object, array, …) has its own editor class. **Step configs** are resolved by property name against committed `*.schema.json` files — no per-step Delphi registration required unless you want custom UI.

```text
Kind-based (Spring resolve by name):
  TSchemaEditorKeys.ForNode(schemaNode)  →  "string" | "object" | …
  GlobalContainer.Resolve<ISchemaPropertyEditor>(key)

Step config (convention-based):
  step_config.<name>  →  TryLoadStepRoot(name)  →  <name>.schema.json
  Optional Spring override by schema root title (e.g. MethylDetectorConfig)
  Else TTypedStepSchemaEditor.Create(name)
```

| Unit | Role |
|------|------|
| `UI/Editors/EditorTypes.pas` | `ISchemaPropertyEditor`, `TPropertyRow` |
| `UI/Editors/SchemaEditorRegistry.pas` | Resolve editor by schema node (or `$ref` path override) |
| `UI/Editors/SchemaEditorRegistration.pas` | Register all editors with Spring4D at startup |
| `UI/Editors/TypedStepSchemaEditor.pas` | Generic typed step editor (loads committed step schema by id) |
| `Schema/JsonSchemaLoader.pas` | Parse schema, `$ref`/`$defs`, nullable `anyOf`, `oneOf`+`discriminator` |
| `Schema/SchemaNode.pas` | Internal schema meta-tree |
| `Data/JsonPath.pas` | JSON pointer get/set |
| `UI/PropertyEditorForm.pas` | Recursive property grid shell (rows + validation) |
| `UI/ArrayEditorForm.pas` | Array list + nested object editor |
| `UI/DictEditorForm.pas` | Open `additionalProperties` maps |
| `App/MainForm.pas` | Schema catalog, document load/save |

### Adding a custom editor

1. Implement `ISchemaPropertyEditor` (subclass `TAbstractSchemaEditor`).
2. Add a string constant in `SchemaEditorKeys` if it is a new *kind* key, or use the schema root **`title`** for step overrides.
3. Register in `SchemaEditorRegistration.EnsureRegistered`:

```delphi
GlobalContainer.RegisterType<ISchemaPropertyEditor, TMyCustomSchemaEditor>
  ('myCustomKey').AsTransient;
```

4. Optional: register by JSON Schema root **`title`** to override the generic typed step editor for one step:

```delphi
GlobalContainer.RegisterType<ISchemaPropertyEditor, TDetectionStepEditor>
  ('MethylDetectorConfig').AsTransient;
```

`TSchemaEditorRegistry.Resolve` checks `$ref`, then **`title`** (Spring), then typed step by title, then kind key.

### Step configs in `project_config`

Under `step_config`, each key (e.g. `detection`, `mapper`, `predictor`, `validation`) is matched to a schema file under the schemas root:

| Property name | Schema file (default) |
|---------------|------------------------|
| `<name>` | `<name>.schema.json` |
| `validation` | `validation.schema.json` |
| `progression` | `progression.schema.json` |
| `validator` (deprecated) | `predictor.schema.json` |

When the file exists, `ResolveProperty` loads that schema and opens the recursive property editor. **New steps only need a committed schema file** — run `methyl-export-config-schemas` in Python; no Delphi change unless you want custom summary UI.

Register a Spring named service only when the generic typed editor is not enough (see `TDetectionStepEditor`).

### Example: `TDetectionStepEditor`

Registered in Spring as **`MethylDetectorConfig`**. It overrides the generic `TTypedStepSchemaEditor` for detection only (custom summary line). All other steps use `TTypedStepSchemaEditor` automatically when their schema file is present.

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
