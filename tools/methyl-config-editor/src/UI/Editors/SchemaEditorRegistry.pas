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
    class function TryResolveTypedStep(const AStepId: string;
      out AEditor: ISchemaPropertyEditor): Boolean;
  end;

implementation

uses
  System.SysUtils,
  Spring.Container,
  SchemaEditorKeys,
  SchemaEditorRegistration,
  TypedStepSchemas,
  TypedStepSchemaEditor;

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

class function TSchemaEditorRegistry.TryResolveTypedStep(const AStepId: string;
  out AEditor: ISchemaPropertyEditor): Boolean;
var
  StepRoot: TSchemaNode;
begin
  AEditor := nil;
  Result := False;
  if not TTypedStepSchemas.TryLoadStepRoot(AStepId, StepRoot) then
    Exit;
  if (StepRoot.Title <> '') and TryResolveByName(StepRoot.Title, AEditor) then
    Exit(True);
  AEditor := TTypedStepSchemaEditor.Create(AStepId);
  Result := True;
end;

class function TSchemaEditorRegistry.Resolve(ANode: TSchemaNode): ISchemaPropertyEditor;
var
  Key: string;
  StepId: string;
begin
  TSchemaEditorRegistration.EnsureRegistered;
  if Assigned(ANode) and (ANode.RefPath <> '') and
    TryResolveByName(ANode.RefPath, Result) then
    Exit;
  if Assigned(ANode) and (ANode.Title <> '') then
  begin
    if TryResolveByName(ANode.Title, Result) then
      Exit;
    StepId := TTypedStepSchemaEditor.StepIdFromNode(ANode);
    if (StepId <> '') and TryResolveTypedStep(StepId, Result) then
      Exit;
  end;
  Key := TSchemaEditorKeys.ForNode(ANode);
  if not TryResolveByName(Key, Result) then
    raise Exception.CreateFmt('No schema property editor registered for key: %s', [Key]);
end;

class function TSchemaEditorRegistry.ResolveProperty(const APropertyName: string;
  ANode: TSchemaNode): ISchemaPropertyEditor;
begin
  if TryResolveTypedStep(APropertyName, Result) then
    Exit;
  Result := Resolve(ANode);
end;

end.
