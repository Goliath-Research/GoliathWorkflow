unit SchemaEditorRegistration;

interface

type
  TSchemaEditorRegistration = class
  private
    class var FRegistered: Boolean;
    class function IsKnownKindKey(const AKey: string): Boolean; static;
  public
    class procedure EnsureRegistered;
    class function IsRegisteredEditorName(const AName: string): Boolean;
  end;

implementation

uses
  System.SysUtils,
  System.TypInfo,
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
  DiscriminatorSchemaEditor;

class function TSchemaEditorRegistration.IsKnownKindKey(const AKey: string): Boolean;
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
    SameStr(AKey, TSchemaEditorKeys.DiscriminatorKey);
end;

class function TSchemaEditorRegistration.IsRegisteredEditorName(const AName: string): Boolean;
begin
  if AName = '' then
    Exit(False);
  EnsureRegistered;
  if IsKnownKindKey(AName) then
    Exit(True);
  Result := GlobalContainer.IsRegistered(TypeInfo(ISchemaPropertyEditor), AName);
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

  GlobalContainer.Build;
  FRegistered := True;
end;

end.
