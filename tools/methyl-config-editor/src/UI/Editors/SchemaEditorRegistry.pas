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
  SchemaEditorKeys,
  SchemaEditorRegistration,
  TypedStepSchemas,
  StringSchemaEditor,
  EnumSchemaEditor,
  BooleanSchemaEditor,
  NumberSchemaEditor,
  IntegerSchemaEditor,
  ObjectSchemaEditor,
  OneOfObjectSchemaEditor,
  ArraySchemaEditor,
  DictionarySchemaEditor,
  DiscriminatorSchemaEditor,
  DetectionStepEditor;

class function TSchemaEditorRegistry.TryResolveByName(const AName: string;
  out AEditor: ISchemaPropertyEditor): Boolean;
begin
  TSchemaEditorRegistration.EnsureRegistered;
  Result := True;
  if AName = TSchemaEditorKeys.StringKey then
    AEditor := TStringSchemaEditor.Create
  else if AName = TSchemaEditorKeys.EnumKey then
    AEditor := TEnumSchemaEditor.Create
  else if AName = TSchemaEditorKeys.BooleanKey then
    AEditor := TBooleanSchemaEditor.Create
  else if AName = TSchemaEditorKeys.IntegerKey then
    AEditor := TIntegerSchemaEditor.Create
  else if AName = TSchemaEditorKeys.NumberKey then
    AEditor := TNumberSchemaEditor.Create
  else if AName = TSchemaEditorKeys.ObjectKey then
    AEditor := TObjectSchemaEditor.Create
  else if AName = TSchemaEditorKeys.OneOfObjectKey then
    AEditor := TOneOfObjectSchemaEditor.Create
  else if AName = TSchemaEditorKeys.ArrayKey then
    AEditor := TArraySchemaEditor.Create
  else if AName = TSchemaEditorKeys.DictionaryKey then
    AEditor := TDictionarySchemaEditor.Create
  else if AName = TSchemaEditorKeys.DiscriminatorKey then
    AEditor := TDiscriminatorSchemaEditor.Create
  else if AName = TSchemaEditorKeys.DetectionConfigKey then
    AEditor := TDetectionStepEditor.Create
  else
  begin
    AEditor := nil;
    Result := False;
  end;
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
  if not TryResolveByName(Key, Result) then
    raise Exception.CreateFmt('No schema property editor registered for key: %s', [Key]);
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
