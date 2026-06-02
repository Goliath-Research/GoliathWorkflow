unit SchemaEditorRegistration;

interface

type
  TSchemaEditorRegistration = class
  private
    class var FRegistered: Boolean;
  public
    class procedure EnsureRegistered;
  end;

implementation

uses
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

class procedure TSchemaEditorRegistration.EnsureRegistered;
begin
  if FRegistered then
    Exit;

  GlobalContainer.RegisterType<ISchemaPropertyEditor, TStringSchemaEditor>
    .Named(TSchemaEditorKeys.StringKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TEnumSchemaEditor>
    .Named(TSchemaEditorKeys.EnumKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TBooleanSchemaEditor>
    .Named(TSchemaEditorKeys.BooleanKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TIntegerSchemaEditor>
    .Named(TSchemaEditorKeys.IntegerKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TNumberSchemaEditor>
    .Named(TSchemaEditorKeys.NumberKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TObjectSchemaEditor>
    .Named(TSchemaEditorKeys.ObjectKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TOneOfObjectSchemaEditor>
    .Named(TSchemaEditorKeys.OneOfObjectKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TArraySchemaEditor>
    .Named(TSchemaEditorKeys.ArrayKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TDictionarySchemaEditor>
    .Named(TSchemaEditorKeys.DictionaryKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TDiscriminatorSchemaEditor>
    .Named(TSchemaEditorKeys.DiscriminatorKey).AsTransient;
  GlobalContainer.RegisterType<ISchemaPropertyEditor, TDetectionStepEditor>
    .Named(TSchemaEditorKeys.DetectionConfigKey).AsTransient;

  FRegistered := True;
end;

end.
