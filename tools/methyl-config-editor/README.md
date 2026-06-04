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
| `UI/PropertyEditorForm.pas` | Recursive property grid shell |
| `UI/ArrayEditorForm.pas` | Array list editor |
| `UI/DictEditorForm.pas` | Open map / `additionalProperties` editor |
| `App/MainForm.pas` | Schema catalog, document load/save |

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

## Example configs

The [`configs/`](configs/) folder may contain sample JSON documents for manual testing. They are not part of the tool design.
