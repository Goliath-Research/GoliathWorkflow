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
  DiscriminatorSchemaEditor;

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
