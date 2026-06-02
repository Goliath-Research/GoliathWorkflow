unit SchemaEditorRegistry;

interface

uses
  SchemaNode,
  ISchemaPropertyEditor;

type
  TSchemaEditorRegistry = class
  public
    class function Resolve(ANode: TSchemaNode): ISchemaPropertyEditor;
    class function TryResolveByName(const AName: string;
      out AEditor: ISchemaPropertyEditor): Boolean;
  end;

implementation

uses
  Spring.Container,
  EditorTypes,
  SchemaEditorKeys,
  SchemaEditorRegistration;

class function TSchemaEditorRegistry.TryResolveByName(const AName: string;
  out AEditor: ISchemaPropertyEditor): Boolean;
begin
  TSchemaEditorRegistration.EnsureRegistered;
  Result := GlobalContainer.CanResolveNamed<ISchemaPropertyEditor>(AName);
  if Result then
    AEditor := GlobalContainer.ResolveNamed<ISchemaPropertyEditor>(AName);
end;

class function TSchemaEditorRegistry.Resolve(ANode: TSchemaNode): ISchemaPropertyEditor;
var
  Key: string;
begin
  TSchemaEditorRegistration.EnsureRegistered;
  if Assigned(ANode) and (ANode.RefPath <> '') and
    TryResolveByName(ANode.RefPath, Result) then
    Exit;
  Key := TSchemaEditorKeys.ForNode(ANode);
  if not GlobalContainer.CanResolveNamed<ISchemaPropertyEditor>(Key) then
    raise Exception.CreateFmt('No schema property editor registered for key: %s', [Key]);
  Result := GlobalContainer.ResolveNamed<ISchemaPropertyEditor>(Key);
end;

end.
