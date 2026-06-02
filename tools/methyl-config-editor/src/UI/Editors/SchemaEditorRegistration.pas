unit SchemaEditorRegistration;

interface

type
  TSchemaEditorRegistration = class
  private
    class var FRegistered: Boolean;
    class function IsKnownKey(const AKey: string): Boolean; static;
  public
    class procedure EnsureRegistered;
    class function IsRegistered(const AKey: string): Boolean;
  end;

implementation

uses
  System.SysUtils,
  Spring.Container,
  EditorTypes,
  SchemaEditorKeys,
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

class function TSchemaEditorRegistration.IsKnownKey(const AKey: string): Boolean;
begin
  Result := SameText(AKey, TSchemaEditorKeys.StringKey) or
    SameText(AKey, TSchemaEditorKeys.EnumKey) or
    SameText(AKey, TSchemaEditorKeys.BooleanKey) or
    SameText(AKey, TSchemaEditorKeys.IntegerKey) or
    SameText(AKey, TSchemaEditorKeys.NumberKey) or
    SameText(AKey, TSchemaEditorKeys.ObjectKey) or
    SameText(AKey, TSchemaEditorKeys.OneOfObjectKey) or
    SameText(AKey, TSchemaEditorKeys.ArrayKey) or
    SameText(AKey, TSchemaEditorKeys.DictionaryKey) or
    SameText(AKey, TSchemaEditorKeys.DiscriminatorKey) or
    SameText(AKey, TSchemaEditorKeys.DetectionConfigKey);
end;

class function TSchemaEditorRegistration.IsRegistered(const AKey: string): Boolean;
begin
  Result := FRegistered and IsKnownKey(AKey);
end;

class procedure TSchemaEditorRegistration.EnsureRegistered;
begin
  if FRegistered then
    Exit;

  GlobalContainer.RegisterType<ISchemaPropertyEditor, TStringSchemaEditor>
    (TSchemaEditorKeys.StringKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TEnumSchemaEditor>
    (TSchemaEditorKeys.EnumKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TBooleanSchemaEditor>
    (TSchemaEditorKeys.BooleanKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TIntegerSchemaEditor>
    (TSchemaEditorKeys.IntegerKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TNumberSchemaEditor>
    (TSchemaEditorKeys.NumberKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TObjectSchemaEditor>
    (TSchemaEditorKeys.ObjectKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TOneOfObjectSchemaEditor>
    (TSchemaEditorKeys.OneOfObjectKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TArraySchemaEditor>
    (TSchemaEditorKeys.ArrayKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TDictionarySchemaEditor>
    (TSchemaEditorKeys.DictionaryKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TDiscriminatorSchemaEditor>
    (TSchemaEditorKeys.DiscriminatorKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TDetectionStepEditor>
    (TSchemaEditorKeys.DetectionConfigKey).AsTransient;

  GlobalContainer.Build;
  FRegistered := True;
end;

end.
