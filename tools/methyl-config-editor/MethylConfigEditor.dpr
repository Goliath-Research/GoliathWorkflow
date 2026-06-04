program MethylConfigEditor;

uses
  Vcl.Forms,
  MainForm in 'src\App\MainForm.pas' {MainForm},
  AppSettings in 'src\App\AppSettings.pas',
  SchemaCatalog in 'src\App\SchemaCatalog.pas',
  JsonSchemaLoader in 'src\Schema\JsonSchemaLoader.pas',
  SchemaDocumentCache in 'src\Schema\SchemaDocumentCache.pas',
  SchemaNode in 'src\Schema\SchemaNode.pas',
  SchemaDocument in 'src\Schema\SchemaDocument.pas',
  SchemaDefaults in 'src\Schema\SchemaDefaults.pas',
  SchemaBranchResolver in 'src\Schema\SchemaBranchResolver.pas',
  SchemaValidator in 'src\Schema\SchemaValidator.pas',
  JsonPath in 'src\Data\JsonPath.pas',
  JsonArrayOps in 'src\Data\JsonArrayOps.pas',
  JsonDocumentModel in 'src\Data\JsonDocumentModel.pas',
  SchemaValueSummary in 'src\UI\SchemaValueSummary.pas',
  EditorTypes in 'src\UI\Editors\EditorTypes.pas',
  PropertyEditorContext in 'src\UI\Editors\PropertyEditorContext.pas',
  SchemaEditorKeys in 'src\UI\Editors\SchemaEditorKeys.pas',
  SchemaEditorRegistry in 'src\UI\Editors\SchemaEditorRegistry.pas',
  SchemaEditorRegistration in 'src\UI\Editors\SchemaEditorRegistration.pas',
  AbstractSchemaEditor in 'src\UI\Editors\AbstractSchemaEditor.pas',
  NullableRowSupport in 'src\UI\Editors\NullableRowSupport.pas',
  ComplexRowSupport in 'src\UI\Editors\ComplexRowSupport.pas',
  StringSchemaEditor in 'src\UI\Editors\StringSchemaEditor.pas',
  EnumSchemaEditor in 'src\UI\Editors\EnumSchemaEditor.pas',
  BooleanSchemaEditor in 'src\UI\Editors\BooleanSchemaEditor.pas',
  NumberSchemaEditor in 'src\UI\Editors\NumberSchemaEditor.pas',
  IntegerSchemaEditor in 'src\UI\Editors\IntegerSchemaEditor.pas',
  ObjectSchemaEditor in 'src\UI\Editors\ObjectSchemaEditor.pas',
  OneOfObjectSchemaEditor in 'src\UI\Editors\OneOfObjectSchemaEditor.pas',
  ArraySchemaEditor in 'src\UI\Editors\ArraySchemaEditor.pas',
  DictionarySchemaEditor in 'src\UI\Editors\DictionarySchemaEditor.pas',
  DiscriminatorSchemaEditor in 'src\UI\Editors\DiscriminatorSchemaEditor.pas',
  PropertyEditorForm in 'src\UI\PropertyEditorForm.pas' {PropertyEditorForm},
  ArrayEditorForm in 'src\UI\ArrayEditorForm.pas' {ArrayEditorForm},
  DictEditorForm in 'src\UI\DictEditorForm.pas' {DictEditorForm},
  Vcl.Themes,
  Vcl.Styles;

{$R *.res}

begin
  Application.Initialize;
  Application.MainFormOnTaskbar := True;
  TStyleManager.TrySetStyle('Aqua Light Slate');
  Application.Title := 'JSON Schema Editor';
  TSchemaEditorRegistration.EnsureRegistered;
  Application.CreateForm(TMainForm, MainFormInstance);
  Application.Run;
end.
