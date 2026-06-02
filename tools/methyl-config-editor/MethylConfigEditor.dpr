program MethylConfigEditor;

uses
  Vcl.Forms,
  MainForm in 'src\App\MainForm.pas' {MainForm},
  AppSettings in 'src\App\AppSettings.pas',
  SchemaCatalog in 'src\App\SchemaCatalog.pas',
  JsonSchemaLoader in 'src\Schema\JsonSchemaLoader.pas',
  SchemaNode in 'src\Schema\SchemaNode.pas',
  SchemaDocument in 'src\Schema\SchemaDocument.pas',
  SchemaDefaults in 'src\Schema\SchemaDefaults.pas',
  SchemaBranchResolver in 'src\Schema\SchemaBranchResolver.pas',
  SchemaValidator in 'src\Schema\SchemaValidator.pas',
  JsonPath in 'src\Data\JsonPath.pas',
  JsonDocumentModel in 'src\Data\JsonDocumentModel.pas',
  SchemaValueSummary in 'src\UI\SchemaValueSummary.pas',
  PropertyEditorForm in 'src\UI\PropertyEditorForm.pas' {PropertyEditorForm},
  ArrayEditorForm in 'src\UI\ArrayEditorForm.pas' {ArrayEditorForm},
  DictEditorForm in 'src\UI\DictEditorForm.pas' {DictEditorForm};

{$R *.res}

begin
  Application.Initialize;
  Application.MainFormOnTaskbar := True;
  Application.Title := 'MethylPipeline Config Editor';
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
end.
