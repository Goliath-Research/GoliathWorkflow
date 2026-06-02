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
  Spring.Container,
  SchemaEditorKeys,
  SchemaEditorRegistration,
  TypedStepSchemas;

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
  if Assigned(ANode) and (ANode.Title <> '') and
    TryResolveByName(ANode.Title, Result) then
    Exit;
  Key := TSchemaEditorKeys.ForNode(ANode);
  if not GlobalContainer.CanResolveNamed<ISchemaPropertyEditor>(Key) then
    raise Exception.CreateFmt('No schema property editor registered for key: %s', [Key]);
  Result := GlobalContainer.ResolveNamed<ISchemaPropertyEditor>(Key);
end;

class function TSchemaEditorRegistry.ResolveProperty(const APropertyName: string;
  ANode: TSchemaNode): ISchemaPropertyEditor;
var
  StepKey: string;
  StepRoot: TSchemaNode;
begin
  if TSchemaEditorKeys.IsTypedStepProperty(APropertyName) then
  begin
    StepKey := TSchemaEditorKeys.TypedStepEditorKey(APropertyName);
    if (StepKey <> '') and TryResolveByName(StepKey, Result) and
      TTypedStepSchemas.TryLoadStepRoot(APropertyName, StepRoot) then
      Exit;
  end;
  Result := Resolve(ANode);
end;

end.
