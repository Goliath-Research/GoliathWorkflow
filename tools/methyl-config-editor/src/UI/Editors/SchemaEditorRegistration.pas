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
  Result := SameStr(AKey, TSchemaEditorKeys.StringKey) or
    SameStr(AKey, TSchemaEditorKeys.EnumKey) or
    SameStr(AKey, TSchemaEditorKeys.BooleanKey) or
    SameStr(AKey, TSchemaEditorKeys.IntegerKey) or
    SameStr(AKey, TSchemaEditorKeys.NumberKey) or
    SameStr(AKey, TSchemaEditorKeys.ObjectKey) or
    SameStr(AKey, TSchemaEditorKeys.OneOfObjectKey) or
    SameStr(AKey, TSchemaEditorKeys.ArrayKey) or
    SameStr(AKey, TSchemaEditorKeys.DictionaryKey) or
    SameStr(AKey, TSchemaEditorKeys.DiscriminatorKey) or
    SameStr(AKey, TSchemaEditorKeys.DetectionConfigKey);
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
