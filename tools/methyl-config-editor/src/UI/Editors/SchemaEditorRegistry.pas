unit SchemaEditorRegistry;

interface

uses
  SchemaNode,
  EditorTypes;

type
  TSchemaEditorRegistry = class
  public
    class function Resolve(ANode: TSchemaNode): ISchemaPropertyEditor;
    class function ResolveProperty(const APropertyName: string;
      ANode: TSchemaNode): ISchemaPropertyEditor;
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
  TSchemaEditorRegistration.EnsureRegistered;
  AEditor := nil;
  Result := False;
  if not TSchemaEditorRegistration.IsRegistered(AName) then
    Exit;
  AEditor := GlobalContainer.Resolve<ISchemaPropertyEditor>(AName);
  Result := Assigned(AEditor);
end;

class function TSchemaEditorRegistry.Resolve(ANode: TSchemaNode): ISchemaPropertyEditor;
var
  Key: string;
begin
  TSchemaEditorRegistration.EnsureRegistered;
  Key := TSchemaEditorKeys.ForNode(ANode);
  if not TryResolveByName(Key, Result) then
    raise Exception.CreateFmt('No schema property editor registered for key: %s', [Key]);
end;

class function TSchemaEditorRegistry.ResolveProperty(const APropertyName: string;
  ANode: TSchemaNode): ISchemaPropertyEditor;
begin
  Result := Resolve(ANode);
end;

end.
