# MethylPipeline Config Editor (Delphi VCL 11+)

Dynamic JSON config editor for MethylPipeline. Loads committed JSON Schema artifacts from [`schemas/config/`](../../schemas/config/) and edits any matching JSON document using a **recursive property editor**: one row per property, with modal nested editors for objects, arrays, and dictionaries.

No Delphi class codegen — schemas from `methyl-export-config-schemas` drive the UI at runtime.

## Requirements

- Delphi 11 or later (VCL, Win32/Win64)
- DUnitX (for tests, optional)

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

| Unit | Role |
|------|------|
| `Schema/JsonSchemaLoader.pas` | Parse schema, `$ref`/`$defs`, nullable `anyOf`, `oneOf`+`discriminator` |
| `Schema/SchemaNode.pas` | Internal schema meta-tree |
| `Data/JsonPath.pas` | JSON pointer get/set |
| `UI/PropertyEditorForm.pas` | Recursive property grid (one form class, many modals) |
| `UI/ArrayEditorForm.pas` | Array list + nested object editor |
| `UI/DictEditorForm.pas` | Open `additionalProperties` maps |
| `App/MainForm.pas` | Schema catalog, document load/save |

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
