unit SchemaEditorRegistry;

interface

uses
  SchemaNode,
  EditorTypes;

type
  TSchemaEditorRegistry = class
  public
    class function Resolve(ANode: TSchemaNode): ISchemaPropertyEditor;
    class function TryResolveByName(const AName: string;
      out AEditor: ISchemaPropertyEditor): Boolean;
  end;

implementation

uses
  System.SysUtils,
  Spring.Container,
  SchemaEditorKeys,
  SchemaEditorRegistration;

class function TSchemaEditorRegistry.TryResolveByName(const AName: string;
  out AEditor: ISchemaPropertyEditor): Boolean;
begin
  AEditor := nil;
  Result := False;
  if not TSchemaEditorRegistration.IsRegisteredEditorName(AName) then
    Exit;
  TSchemaEditorRegistration.EnsureRegistered;
  try
    AEditor := GlobalContainer.Resolve<ISchemaPropertyEditor>(AName);
    Result := Assigned(AEditor);
  except
    AEditor := nil;
    Result := False;
  end;
end;

class function TSchemaEditorRegistry.Resolve(ANode: TSchemaNode): ISchemaPropertyEditor;
var
  Key: string;
begin
  Key := TSchemaEditorKeys.ForNode(ANode);
  if not TryResolveByName(Key, Result) then
    raise Exception.CreateFmt('No schema property editor registered for key: %s', [Key]);
end;

end.
